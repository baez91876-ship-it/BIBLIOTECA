const { existsSync, readdirSync } = require("node:fs");
const path = require("node:path");
const { spawn } = require("node:child_process");

const projectRoot = path.resolve(__dirname, "..");
const packageName = readdirSync(projectRoot).find(
  (name) => name.toLowerCase() === "app"
);
if (!packageName) {
  console.error("No se encontró la carpeta de la aplicación (app/ o APP/).");
  process.exit(1);
}

const virtualEnvPython = path.join(
  projectRoot,
  ".venv",
  process.platform === "win32" ? "Scripts" : "bin",
  process.platform === "win32" ? "python.exe" : "python"
);
const python = existsSync(virtualEnvPython)
  ? virtualEnvPython
  : process.platform === "win32"
    ? "python"
    : "python3";

const server = spawn(
  python,
  ["-m", "uvicorn", `${packageName}.main:app`, "--reload"],
  { cwd: projectRoot, stdio: "inherit" }
);

server.on("error", (error) => {
  console.error(`No se pudo iniciar Python (${python}): ${error.message}`);
  process.exitCode = 1;
});

server.on("exit", (code, signal) => {
  process.exitCode = code ?? (signal ? 1 : 0);
});
