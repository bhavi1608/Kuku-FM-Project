"""Kuku FM Promo Finder — Groq-connected promo ranking prototype."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from groq import Groq, APIStatusError, AuthenticationError

from parser.screenplay_parser import parse_directory
from candidate.window_generator import generate_candidates
from ai.groq_evaluator import evaluate_candidate, weighted_score, DEFAULT_MODEL
from evaluation.validator import validate_promo

load_dotenv()
st.set_page_config(page_title="Kuku FM | Promo Finder", page_icon="🎬", layout="wide")
st.title("🎬 Kuku FM — Promo Finder")
st.caption("Upload the complete screenplay input pack to identify, evaluate and rank promo candidates.")

api_key = ""
try:
    api_key = st.secrets.get("GROQ_API_KEY", "")
except Exception:
    pass
api_key = api_key or os.getenv("GROQ_API_KEY", "")

if not api_key:
    st.error("Groq API key not found. Configure GROQ_API_KEY in your local .env file or Streamlit Secrets.")
    st.code("GROQ_API_KEY=your_actual_groq_api_key\nGROQ_MODEL=openai/gpt-oss-20b", language="bash")
    st.info("Do not paste your key into app.py or commit .env to GitHub.")
    st.stop()

# Query the account for models it can actually see; avoid hard-coding an inaccessible model.
client = Groq(api_key=api_key)
try:
    available_models = sorted({
        model.id for model in client.models.list().data
        if model.id and not any(term in model.id.lower() for term in (
            "whisper", "guard", "orpheus", "embedding", "tts", "speech"
        ))
    })
except AuthenticationError:
    st.error("Groq rejected the configured API key. Check the key in .env / Streamlit Secrets.")
    st.stop()
except Exception as exc:
    st.error(f"Could not retrieve models available to this Groq account: {exc}")
    st.stop()

if not available_models:
    st.error("Groq returned no text-generation models for this account.")
    st.stop()

preferred = os.getenv("GROQ_MODEL", DEFAULT_MODEL)
default_index = available_models.index(preferred) if preferred in available_models else (
    available_models.index("openai/gpt-oss-20b")
    if "openai/gpt-oss-20b" in available_models else 0
)

with st.sidebar:
    st.header("Evaluation settings")
    top_n = st.number_input("Number of promos to display", min_value=1, max_value=10, value=10)
    max_candidates = st.slider(
        "Candidate clips to evaluate",
        min_value=5, max_value=60, value=30, step=5,
        help="Number of candidate clips sent to Groq. More candidates give the ranking a larger pool, but use more free-tier quota."
    )
    st.caption(
        f"This controls how many candidate clips Groq evaluates, not characters or episodes. "
        f"The Python generator may create hundreds of candidates; only the highest-priority "
        f"{max_candidates} are sent to Groq in this run."
    )
    model_name = st.selectbox(
        "Groq model available to your account",
        options=available_models,
        index=default_index,
        help="Models are loaded from your Groq account rather than assumed in the code."
    )
    st.caption("Groq limits are measured in requests and tokens. Your exact quotas are shown in Groq Console.")

uploaded_files = st.file_uploader(
    "Upload screenplay episode files (.txt) — complete input pack; episode count is variable.",
    type=["txt"], accept_multiple_files=True,
)
if not uploaded_files:
    st.info("Upload the screenplay files to begin. There is no fixed episode count.")
    st.stop()

if st.button("Generate and rank promos", type="primary", use_container_width=True):
    with tempfile.TemporaryDirectory(prefix="kuku_input_") as temp_dir:
        input_dir = Path(temp_dir)
        for uploaded in uploaded_files:
            (input_dir / Path(uploaded.name).name).write_bytes(uploaded.getvalue())

        with st.spinner("Parsing screenplay input pack..."):
            parsed = parse_directory(input_dir)
        st.write(
            f"Parsed {parsed['episode_count']} episodes, "
            f"{parsed['scene_count']} scenes, and {parsed['event_count']} events."
        )
        if not parsed["run_validation"]["all_episodes_valid"]:
            st.error("Parsing errors found. Resolve them before promo generation.")
            st.json(parsed["run_validation"])
            st.stop()

        with st.spinner("Generating timestamp-grounded candidate windows..."):
            candidates = generate_candidates(parsed)
        st.write(f"Generated {len(candidates)} event-aligned candidate windows.")

        candidates = sorted(
            candidates, key=lambda c: c["heuristic_priority"], reverse=True
        )[:int(max_candidates)]

        # Verify that the selected model is still available before any completion calls.
        current_ids = {m.id for m in client.models.list().data}
        if model_name not in current_ids:
            st.error(
                f"The model '{model_name}' is no longer available to this account. "
                "Refresh the app and select a model from the updated list."
            )
            st.stop()

        evaluated = []
        validation_rejected = []
        api_failed = []
        progress = st.progress(0)
        status = st.empty()
        for index, candidate in enumerate(candidates, 1):
            status.write(f"Groq evaluating candidate {index}/{len(candidates)}...")
            try:
                evaluation = evaluate_candidate(candidate, client=client, model=model_name)
                validation = validate_promo(candidate, evaluation)
                if validation["valid"]:
                    evaluated.append({
                        **candidate,
                        "promo_type": "continuous",
                        "evaluation": evaluation,
                        "weighted_score": weighted_score(evaluation),
                        "validation": validation,
                    })
                else:
                    validation_rejected.append({
                        "candidate_id": candidate["candidate_id"],
                        "reasons": validation.get("errors", []),
                    })
            except AuthenticationError:
                st.error("Groq authentication failed during evaluation. Check your API key.")
                st.stop()
            except APIStatusError as exc:
                if exc.status_code == 404:
                    st.error(f"Groq cannot access model '{model_name}'. Select another listed model.")
                    st.stop()
                if exc.status_code == 429:
                    st.error(
                        "Groq free-tier rate limit reached. Reduce 'Candidates sent to Groq', "
                        "wait for the quota reset, then run again."
                    )
                    st.stop()
                api_failed.append({
                    "candidate_id": candidate["candidate_id"],
                    "reason": f"HTTP {exc.status_code}",
                })
                st.warning(f"Candidate {candidate['candidate_id']} failed (HTTP {exc.status_code}).")
            except Exception as exc:
                api_failed.append({
                    "candidate_id": candidate["candidate_id"],
                    "reason": str(exc),
                })
                st.warning(f"Candidate {candidate['candidate_id']} failed: {exc}")
            progress.progress(index / max(len(candidates), 1))

        evaluated.sort(key=lambda item: item["weighted_score"], reverse=True)
        selected = []
        duplicate_removed = []
        for item in evaluated:
            is_duplicate = False
            for existing in selected:
                if item["episode_id"] == existing["episode_id"] and item["scene_id"] == existing["scene_id"]:
                    intersection = max(
                        0,
                        min(item["end_seconds"], existing["end_seconds"])
                        - max(item["start_seconds"], existing["start_seconds"]),
                    )
                    union = max(item["end_seconds"], existing["end_seconds"]) - min(
                        item["start_seconds"], existing["start_seconds"]
                    )
                    # Only suppress near-identical clips, not merely overlapping ones.
                    if union and intersection / union >= 0.92:
                        is_duplicate = True
                        break
            if is_duplicate:
                duplicate_removed.append(item["candidate_id"])
            else:
                selected.append(item)
            if len(selected) >= int(top_n):
                break

        st.session_state["promo_results"] = selected
        st.session_state["parsed_result"] = parsed
        st.session_state["evaluated_count"] = len(evaluated)
        st.session_state["submitted_count"] = len(candidates)
        st.session_state["validation_rejected"] = validation_rejected
        st.session_state["api_failed"] = api_failed
        st.session_state["duplicate_removed"] = duplicate_removed
        st.session_state["generated_count"] = len(candidates)

if "promo_results" in st.session_state:
    results = st.session_state["promo_results"]
    st.subheader("Generation diagnostics")
    d1, d2, d3, d4, d5 = st.columns(5)
    d1.metric("Sent to Groq", st.session_state.get("submitted_count", 0))
    d2.metric("AI evaluations passed", st.session_state.get("evaluated_count", 0))
    d3.metric("Validation rejected", len(st.session_state.get("validation_rejected", [])))
    d4.metric("API failures", len(st.session_state.get("api_failed", [])))
    d5.metric("Duplicates removed", len(st.session_state.get("duplicate_removed", [])))
    st.caption(
        "The candidate generator creates the pool; Groq evaluates only the selected budget. "
        "Validation and duplicate filtering can reduce the final number further."
    )
    st.subheader("Top ranked promos")
    if not results:
        st.error("No candidates passed evaluation and validation. No AI ranking is available for this run.")
    else:
        st.caption(
            f"Showing {len(results)} distinct promos from "
            f"{st.session_state.get('evaluated_count', 0)} candidates that passed validation."
        )
        if len(results) < 10:
            st.warning(
                f"Only {len(results)} promos were available after evaluation and filtering. "
                "Increase the Groq candidate budget or use more screenplay episodes; "
                "the app will not fabricate extra recommendations."
            )
        summary = []
        for rank, promo in enumerate(results, 1):
            summary.append({
                "Rank": rank,
                "Promo ID": promo["candidate_id"],
                "Episode": promo["episode_id"],
                "Scene": promo["scene_id"],
                "Type": promo["promo_type"],
                "Start": promo["start_time"],
                "End": promo["end_time"],
                "Duration (sec)": promo["duration_seconds"],
                "Weighted score": promo["weighted_score"],
                "Curiosity": promo["evaluation"]["curiosity"],
                "Validation": "Passed",
            })
        st.dataframe(pd.DataFrame(summary), use_container_width=True, hide_index=True)

        for rank, promo in enumerate(results, 1):
            ev = promo["evaluation"]
            with st.expander(
                f"#{rank} | {promo['episode_id']} | {promo['start_time']}–"
                f"{promo['end_time']} | Score {promo['weighted_score']}"
            ):
                st.markdown(f"**Hook:** {ev.get('hook_explanation', '')}")
                st.markdown(f"**Cliffhanger:** {ev.get('cliffhanger_explanation', '')}")
                st.markdown(f"**Curiosity question:** {ev.get('curiosity_question', '')}")
                st.markdown(f"**Summary:** {ev.get('narrative_summary', '')}")
                st.markdown(f"**Why it works:** {ev.get('why_it_works', '')}")
                st.json({
                    "scores": {k: ev[k] for k in (
                        "hook_strength", "curiosity", "immediate_comprehensibility",
                        "emotional_intensity", "narrative_progression"
                    )},
                    "source_event_ids": promo["event_ids"],
                    "validation": promo["validation"],
                })

        export = []
        for rank, promo in enumerate(results, 1):
            ev = promo["evaluation"]
            export.append({
                "promo_id": promo["candidate_id"],
                "rank": rank,
                "episode_ids": [promo["episode_id"]],
                "promo_type": promo["promo_type"],
                "total_duration_seconds": promo["duration_seconds"],
                "segments": [{
                    "segment_order": 1,
                    "episode_id": promo["episode_id"],
                    "scene_id": promo["scene_id"],
                    "start_time": promo["start_time"],
                    "end_time": promo["end_time"],
                    "duration_seconds": promo["duration_seconds"],
                    "source_event_ids": promo["event_ids"],
                }],
                "hook": ev.get("hook_explanation", ""),
                "cliffhanger": ev.get("cliffhanger_explanation", ""),
                "curiosity_question": ev.get("curiosity_question", ""),
                "narrative_summary": ev.get("narrative_summary", ""),
                "why_it_works": ev.get("why_it_works", ""),
                "scores": {k: ev[k] for k in (
                    "hook_strength", "curiosity", "immediate_comprehensibility",
                    "emotional_intensity", "narrative_progression"
                )},
                "weighted_score": promo["weighted_score"],
                "validation": promo["validation"],
            })
        json_bytes = json.dumps({
            "schema_version": "1.0.0",
            "episode_count": st.session_state["parsed_result"]["episode_count"],
            "promos": export,
        }, ensure_ascii=False, indent=2).encode("utf-8")
        st.download_button(
            "Download ranked promos (JSON)", json_bytes,
            "ranked_promos.json", "application/json"
        )
        st.download_button(
            "Download ranked promos (CSV)",
            pd.DataFrame(summary).to_csv(index=False).encode("utf-8"),
            "ranked_promos.csv", "text/csv"
        )
