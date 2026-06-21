# App Tag Auditor

An automated solution to audit Firebase Analytics events in Android-only applications using a multi-agent AI system and Streamlit. This app requires no source code repository access; it decompiles the target APK to identify event triggers, plans and executes crawls to fire those triggers, captures the event logs, validates them, and updates a Google Sheet with the status.

## 8-Agent Pipeline

1. **Schema Reader Agent (`agents.agent1_schema_reader`)**: Parses the expected event schema and extracts keywords.
2. **Codebase Mapper Agent (`agents.agent2_codebase_mapper`)**: Decompiles the APK and locates Firebase event trigger sites and screen breadcrumbs.
3. **Crawl Planner Agent (`agents.agent3_crawl_planner`)**: Generates crawl plans to reach and trigger specific analytics events.
4. **Crawl Executor Agent (`agents.agent4_crawl_executor`)**: Executes UI interactions on an Android device or emulator via Appium.
5. **Log Capture Agent (`agents.agent5_log_capture`)**: Captures and filters Firebase analytics logs via `adb logcat` and streams them.
6. **Telemetry Validator Agent (`agents.agent6_telemetry_validator`)**: Compares actual parameters in logs against the expected schema.
7. **Runtime Validator Agent (`agents.agent7_runtime_validator`)**: Confirms whether the target UI actions/triggers actually fired during run.
8. **Validation Combiner Agent (`agents.agent8_validation_combiner`)**: Merges validation results into a consolidated report and writes to Google Sheets.


## Prerequisites

* **JADX Decompiler**: Required for real-APK decompilation. Install via:
  * **macOS**: `brew install jadx`
  * **GitHub**: [skylot/jadx](https://github.com/skylot/jadx)
  Ensure `jadx` is available on your system `PATH`, or set `JADX_PATH` inside your `.env` configuration file pointing to your custom installation.

## Running the Project


### Scaffolding Verification
To verify the stubs work and all dependencies resolve:
1. Initialize the virtual environment and install packages.
2. Run the Streamlit UI:
   ```bash
   streamlit run app_tag_auditor/frontend/app.py
   ```

### Standalone Agent Execution (Debugging)
Each agent is runnable as a standalone script to verify execution and catch unimplemented stubs:
```bash
python -m app_tag_auditor.agents.agent1_schema_reader
```
or from the `app_tag_auditor` directory:
```bash
python -m agents.agent1_schema_reader
```
