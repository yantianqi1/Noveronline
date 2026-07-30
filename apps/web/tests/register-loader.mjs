/**
 * Registers the test-suite ESM loader (tests/alias-loader.mjs) on the main
 * thread. Used as `node --import ./tests/register-loader.mjs --test …` from the
 * "test" script so every test file can import app sources that rely on the `@/`
 * path alias and extensionless relative imports.
 */
import { register } from "node:module";

register("./alias-loader.mjs", import.meta.url);
