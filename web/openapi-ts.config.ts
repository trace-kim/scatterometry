import { defineConfig } from "@hey-api/openapi-ts";

// Types only: requests go through src/api/client.ts, which also decodes the .npz
// array responses that a generated SDK would not know how to read.
export default defineConfig({
  input: "openapi.json",
  output: "src/api/gen",
  plugins: ["@hey-api/typescript"],
});
