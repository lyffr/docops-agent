# Windows Executable

DocOps Agent 0.3 can be distributed as a single Windows executable. The recipient does not need
Python, Docker, or the source repository.

## Run the application

Use a 64-bit Windows 10 or Windows 11 machine and double-click `DocOpsAgent.exe`.

The executable performs these steps automatically:

1. Selects unused loopback ports.
2. Starts the FastAPI service on `127.0.0.1`.
3. Starts the Streamlit UI on `127.0.0.1`.
4. Opens the UI in the default browser.
5. Displays a native Windows control dialog.

Keep the control dialog open while using the application. Select **OK** to reopen the browser UI;
select **Cancel** or close the dialog to stop both services. The first launch can take several
seconds because the one-file bundle must unpack its embedded runtime, and antivirus scanning may
add more delay.

The desktop build deliberately binds only to the local computer and disables API authentication.
It is intended for a single Windows user, demonstrations, and local knowledge bases. Use the
Docker deployment with authentication and TLS for shared or internet-facing installations.

## Data, configuration, and logs

The executable never writes its database into the temporary unpack directory. Persistent files
are stored under:

```text
%LOCALAPPDATA%\DocOpsAgent\
├── config.env
├── data\docops.db
└── logs\
    ├── api.log
    └── ui.log
```

Uploaded document text, approvals, tickets, and audit events are stored in `data\docops.db`.
Back up that file while the application is stopped.

The default `config.env` uses the offline extractive generator. To enable an OpenAI-compatible
model, close DocOps Agent, edit the file, and set all four values:

```dotenv
DOCOPS_LLM_PROVIDER=openai-compatible
DOCOPS_LLM_BASE_URL=https://your-endpoint.example/v1
DOCOPS_LLM_API_KEY=your-secret
DOCOPS_LLM_MODEL=your-model
```

Restart the executable after changing the configuration. The API key is stored as plain text in
the current Windows user's profile, so protect the Windows account and do not share `config.env`.

## Build from source

Building requires 64-bit Windows, Python 3.10 or newer, and the project virtual environment. From
the repository root, run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_windows.ps1
```

The build script installs the exact packages in `requirements-build.lock`, runs tests and Ruff,
and then creates:

```text
dist\DocOpsAgent.exe
```

For an already-tested local iteration, use `-SkipTests`. Release builds should not skip tests.

The executable includes Python, FastAPI, Streamlit, parsing dependencies, and the demonstration
document, so a file size around 90–100 MB is expected. PyInstaller builds are platform-specific;
the Windows executable must be built on Windows.

## Automated build

The `Windows Executable` GitHub Actions workflow runs on version tags and can also be started
manually. It tests the code, builds the one-file executable, runs the executable's embedded smoke
test, and uploads `DocOpsAgent.exe` as a workflow artifact.

The generated file is not code-signed. Windows SmartScreen can warn users about unsigned files.
Use an Authenticode certificate and sign the final executable before distributing it broadly.
