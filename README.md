Kuku FM Promo Finder
An AI-assisted Streamlit application that analyzes timestamped screenplay text files, generates event-aligned promo clip candidates, evaluates their promotional strength with Groq, and ranks the strongest distinct candidates.
Features
- Multiple-episode input: Upload one or more screenplay .txt files in a single run.
- Timestamp-aware parsing: Extracts episode, scene, event, and timestamp information from the screenplay files.
- Candidate generation: Creates continuous, event-aligned clip windows with a target duration of 20–60 seconds.
- AI-based evaluation: Uses a Groq-hosted language model to assess each candidate on:
  - Hook strength
  - Curiosity / cliffhanger
  - Immediate comprehensibility
  - Emotional intensity
  - Narrative progression
- Weighted ranking: Ranks candidates using the following scoring weights:
  Evaluation dimension	Weight
  Hook strength	25%
  Curiosity / cliffhanger	30%
  Immediate comprehensibility	15%
  Emotional intensity	15%
  Narrative progression	15%
- Validation and deduplication: Checks candidate duration and timestamp/source grounding, then filters near-identical candidates from the same scene.
- Diagnostics: Shows how many candidates were sent to Groq, passed evaluation, failed validation, encountered API errors, or were removed as duplicates.
- Exports: Download the ranked results as JSON or CSV.
How it works
1. Upload the screenplay episode files.
2. The parser extracts episode, scene, event, and timestamp data.
3. The candidate generator creates continuous 20–60 second windows aligned to screenplay event boundaries.
4. Candidate windows are prioritized and a configurable number are sent to Groq for evaluation.
5. The evaluator returns structured scores and explanations for each candidate.
6. The validator checks the candidate and evaluation output.
7. The application ranks valid candidates, removes near-duplicates, and displays up to the requested number of results.
8. Download the final ranking in JSON or CSV format.
Technology stack
- Python
- Streamlit
- Groq API
- Pandas
- python-dotenv
Project structure
Kuku-FM-Project/
├── app.py
├── requirements.txt
├── .env.example
├── .gitignore
├── ai/
│   ├── __init__.py
│   └── groq_evaluator.py
├── candidate/
│   ├── __init__.py
│   └── window_generator.py
├── parser/
│   ├── __init__.py
│   └── screenplay_parser.py
├── evaluation/
│   ├── __init__.py
│   └── validator.py
├── data/
│   ├── parsed_episodes.json
│   └── samples/
└── tests/
    └── test_parser.py
Requirements
- Python 3.10 or a compatible newer Python version
- A Groq API key
- Internet access for Groq model evaluation
Install dependencies:
pip install -r requirements.txt
Configuration
Create a .env file in the project root. You can copy .env.example and replace the placeholder value:
GROQ_API_KEY=your_actual_groq_api_key
GROQ_MODEL=openai/gpt-oss-20b
The application retrieves the available text-generation models from the configured Groq account and lets you select an available model in the sidebar. GROQ_MODEL is used as the preferred default when that model is available.

Security: Never commit .env or publish your API key. The repository should contain .env.example with placeholder values only. For deployment, configure GROQ_API_KEY as an environment variable in the hosting provider's dashboard.
Run locally
From the project root:
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
Streamlit will print a local URL, usually http://localhost:8501.
Deploy on Render
1. Push the project to a GitHub repository.
2. In the Render dashboard, create a New Web Service and connect the repository.
3. Configure the service:
   Setting	Value
   Runtime	Python 3
   Build command	pip install -r requirements.txt
   Start command	streamlit run app.py --server.port $PORT --server.address 0.0.0.0
4. Add the environment variable GROQ_API_KEY in the Render service settings. Add GROQ_MODEL only if you want to set a preferred default model.
5. Deploy the service and open the URL provided by Render.
Do not upload .env to GitHub or rely on a local .env file being present on Render.
Input format and current scope
The application expects timestamped screenplay text files in the format supported by parser/screenplay_parser.py. Upload the complete set of episode files for the story you want to analyze.

Current implementation limitations:
- The current candidate generator produces continuous clips. Multi-segment promos assembled from separate parts are not implemented in this version.
- The application analyzes screenplay text and its timestamped descriptions. It does not inspect the actual video, audio, acting, shot composition, or edit quality.
- Timestamp and source-grounding checks are based on the parsed screenplay data; they do not independently verify the corresponding media files.
- The requested number of results is a maximum. The app may return fewer if fewer distinct candidates pass evaluation, validation, and duplicate filtering.
- Groq API availability, rate limits, and token limits can affect how many candidates can be evaluated in one run.
Tests
Run the parser tests from the project root:
python -m unittest discover -s tests -v
Repository hygiene
Before pushing changes, check that secrets and local environment files are excluded:
git status
Do not commit .env, virtual environments, cache folders, or API keys.
