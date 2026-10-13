// Regenerate the API types: dump FastAPI's OpenAPI schema with the repo's Python
// environment, then run @hey-api/openapi-ts (see openapi-ts.config.ts).
//   pnpm api:gen
import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";

const web = path.resolve(import.meta.dirname, "..");
const root = path.resolve(web, "..");
const venvPython =
  process.platform === "win32"
    ? path.join(root, ".venv", "Scripts", "python.exe")
    : path.join(root, ".venv", "bin", "python");
const python = existsSync(venvPython) ? venvPython : "python";

execFileSync(python, ["-m", "maskserver.openapi", path.join(web, "openapi.json")], { stdio: "inherit" });
execFileSync("pnpm", ["exec", "openapi-ts"], { stdio: "inherit", cwd: web, shell: process.platform === "win32" });
