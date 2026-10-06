const { defineConfig } = require("@playwright/test");
module.exports = defineConfig({
  testDir: "./e2e",
  use: { baseURL: "http://127.0.0.1:8765", browserName: "chromium" },
  webServer: {
    command: `${process.platform === "win32" ? ".venv\\Scripts\\python.exe" : ".venv/bin/python"} -m uvicorn app.main:app --host 127.0.0.1 --port 8765`,
    url: "http://127.0.0.1:8765/api/health",
    env: { DEMO_MODE: "true" },
    reuseExistingServer: false,
  },
});
