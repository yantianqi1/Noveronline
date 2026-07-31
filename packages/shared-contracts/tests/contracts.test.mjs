import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

import Ajv2020 from "ajv/dist/2020.js";
import ts from "typescript";

import {
  PI_WRITER_WORKFLOW_NAME,
  WRITER_MODES,
  WRITER_MODULE_KEYS,
  WRITER_PUBLIC_EVENT_TYPES,
  WRITER_RUNTIME_EVENT_TYPES,
  WRITER_TASK_QUEUE,
  WRITER_TOOL_NAMES,
  WRITER_WORKFLOW_TYPE
} from "../src/index.js";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = resolve(packageRoot, "../..");
const schemas = {
  writer_workflow_input: loadJSON("schemas/writer-workflow-input.schema.json"),
  writer_tool_request: loadJSON("schemas/writer-tool-request.schema.json"),
  writer_runtime_event: loadJSON("schemas/writer-runtime-event.schema.json"),
  writer_public_event: loadJSON("schemas/writer-public-event.schema.json")
};
const ajv = new Ajv2020({ allErrors: true, strict: true });
const validators = Object.fromEntries(
  Object.entries(schemas).map(([name, schema]) => [name, ajv.compile(schema)])
);

test("Go, Python, and Node serializers satisfy every shared writer contract", () => {
  const fixtureSets = {
    go: runJSON("go", ["run", "./tests/producers/go/main.go"]),
    python: runJSON("python3", ["tests/producers/python.py"]),
    node: runJSON(process.execPath, ["tests/producers/node.mjs"])
  };

  for (const [language, fixtures] of Object.entries(fixtureSets)) {
    for (const [contractName, validate] of Object.entries(validators)) {
      assert.ok(fixtures[contractName], `${language} did not emit ${contractName}`);
      assert.equal(
        validate(fixtures[contractName]),
        true,
        `${language} ${contractName} violates schema: ${ajv.errorsText(validate.errors)}`
      );
    }
  }
});

test("schemas fail closed for missing context, unknown modes/events, and envelope drift", () => {
  const validInput = runJSON(process.execPath, ["tests/producers/node.mjs"]).writer_workflow_input;
  assertInvalid("writer_workflow_input", { ...validInput, tenant_id: "" });
  assertInvalid("writer_workflow_input", { ...validInput, mode: "review" });
  assertInvalid("writer_workflow_input", { ...validInput, unexpected_context: true });
  assertInvalid("writer_workflow_input", {
    ...validInput,
    options: { ...validInput.options, module_key: "legacy_writer_env" }
  });

  const validRuntime = runJSON(process.execPath, ["tests/producers/node.mjs"]).writer_runtime_event;
  assertInvalid("writer_runtime_event", { ...validRuntime, event_type: "writer.mock.succeeded" });
  assertInvalid("writer_runtime_event", { ...validRuntime, sequence: 1 });

  const validTool = runJSON(process.execPath, ["tests/producers/node.mjs"]).writer_tool_request;
  assertInvalid("writer_tool_request", { ...validTool, run_id: "" });
  assertInvalid("writer_tool_request", { ...validTool, tool_name: "manage_world_rule" });
  assertInvalid("writer_tool_request", { ...validTool, actor_user_id: "user-node" });

  const validPublic = runJSON(process.execPath, ["tests/producers/node.mjs"]).writer_public_event;
  assertInvalid("writer_public_event", { ...validPublic, sequence: 0 });
  assertInvalid("writer_public_event", { ...validPublic, tenant_id: "tenant-node" });
});

test("exported constants are generated-equivalent to the schema enums", () => {
  assert.deepEqual(schemas.writer_workflow_input.properties.mode.enum, [...WRITER_MODES]);
  assert.deepEqual(
    schemas.writer_workflow_input.properties.options.properties.module_key.enum,
    [...WRITER_MODULE_KEYS]
  );
  assert.deepEqual(schemas.writer_runtime_event.properties.event_type.enum, [...WRITER_RUNTIME_EVENT_TYPES]);
  assert.deepEqual(schemas.writer_tool_request.properties.tool_name.enum, [...WRITER_TOOL_NAMES]);
  assert.deepEqual(schemas.writer_public_event.properties.event_type.enum, [...WRITER_PUBLIC_EVENT_TYPES]);
  assert.equal(WRITER_WORKFLOW_TYPE, "writer_run");
  assert.equal(PI_WRITER_WORKFLOW_NAME, "PiWriterRunWorkflow");
  assert.equal(WRITER_TASK_QUEUE, "writer-streaming");
});

test("current Go, Pi, and Web consumers cannot drift silently", () => {
  const goContract = runJSON("go", ["run", "./tests/inspectors/go/main.go", repositoryRoot]);
  assert.deepEqual(goContract.constants, {
    PiWriterWorkflowName: PI_WRITER_WORKFLOW_NAME,
    WriterReviewWorkflowType: "writer_review",
    WriterTaskQueue: WRITER_TASK_QUEUE,
    WriterWorkflowType: WRITER_WORKFLOW_TYPE
  });
  assert.deepEqual(goContract.starter_payload, sorted([
    "tenant_id",
    "project_id",
    "run_id",
    "trace_id",
    "requested_by",
    "request_id",
    "mode",
    "chapter_id",
    "scene_id",
    "instruction",
    "options",
    "workflow_type"
  ]));
  assert.deepEqual(goContract.writer_event_json, sorted([
    "event_id", "run_id", "project_id", "sequence", "event_type", "payload", "created_at"
  ]));

  const piRun = parseTypeScript("apps/pi-agent-runtime/src/contracts/writer-run.ts");
  assert.deepEqual(interfacePropertyNames(piRun, "WriterRunInput"), sorted([
    "tenant_id",
    "project_id",
    "run_id",
    "trace_id",
    "requested_by",
    "mode",
    "chapter_id",
    "scene_id",
    "instruction",
    "selected_asset_ids",
    "graph_node_ids",
    "worldline_path_ids",
    "worldline_session_ids",
    "options"
  ]));
  assert.deepEqual(interfacePropertyStringUnion(piRun, "WriterRunInput", "mode"), [...WRITER_MODES]);
  assert.deepEqual(nestedPropertyStringUnion(piRun, "WriterRunInput", "options", "module_key"), [...WRITER_MODULE_KEYS]);

  const piActivities = parseTypeScript("apps/pi-agent-runtime/src/activities/pi-writer-activities.ts");
  assert.deepEqual(typeAliasStringUnion(piActivities, "WriterToolName"), [...WRITER_TOOL_NAMES]);
  assert.deepEqual(
    interfacePropertyStringUnion(piActivities, "RecordWorkflowEventRequest", "event_type"),
    [...WRITER_RUNTIME_EVENT_TYPES]
  );

  const webAPI = parseTypeScript("apps/web/lib/api/writer-types.ts");
  assert.deepEqual(typeAliasPropertyNames(webAPI, "WriterEvent"), sorted([
    "event_id",
    "sequence",
    "event_type",
    "payload",
    "created_at"
  ]));
});

function loadJSON(path) {
  return JSON.parse(readFileSync(join(packageRoot, path), "utf8"));
}

function runJSON(command, args) {
  return JSON.parse(execFileSync(command, args, { cwd: packageRoot, encoding: "utf8" }));
}

function assertInvalid(contractName, value) {
  const validate = validators[contractName];
  assert.equal(validate(value), false, `${contractName} unexpectedly accepted ${JSON.stringify(value)}`);
  assert.ok(validate.errors?.length, `${contractName} rejection must include schema errors`);
}

function parseTypeScript(path) {
  const absolute = join(repositoryRoot, path);
  return ts.createSourceFile(absolute, readFileSync(absolute, "utf8"), ts.ScriptTarget.Latest, true);
}

function interfaceDeclaration(sourceFile, name) {
  const declaration = sourceFile.statements.find(
    (statement) => ts.isInterfaceDeclaration(statement) && statement.name.text === name
  );
  assert.ok(declaration, `interface ${name} was not found in ${sourceFile.fileName}`);
  return declaration;
}

function typeAliasDeclaration(sourceFile, name) {
  const declaration = sourceFile.statements.find(
    (statement) => ts.isTypeAliasDeclaration(statement) && statement.name.text === name
  );
  assert.ok(declaration, `type alias ${name} was not found in ${sourceFile.fileName}`);
  return declaration;
}

function propertyName(member) {
  assert.ok(member.name && ts.isIdentifier(member.name), "contract property must use an identifier name");
  return member.name.text;
}

function interfacePropertyNames(sourceFile, name) {
  return sorted(interfaceDeclaration(sourceFile, name).members.map(propertyName));
}

function typeAliasPropertyNames(sourceFile, name) {
  const declaration = typeAliasDeclaration(sourceFile, name);
  assert.ok(ts.isTypeLiteralNode(declaration.type), `${name} must remain a type literal`);
  return sorted(declaration.type.members.map(propertyName));
}

function interfacePropertyStringUnion(sourceFile, interfaceName, name) {
  const member = interfaceDeclaration(sourceFile, interfaceName).members.find(
    (candidate) => propertyName(candidate) === name
  );
  assert.ok(member?.type, `${interfaceName}.${name} was not found`);
  return stringLiteralUnion(member.type);
}

function nestedPropertyStringUnion(sourceFile, interfaceName, objectName, property) {
  const object = interfaceDeclaration(sourceFile, interfaceName).members.find(
    (candidate) => propertyName(candidate) === objectName
  );
  assert.ok(object?.type && ts.isTypeLiteralNode(object.type), `${interfaceName}.${objectName} must be a type literal`);
  const nested = object.type.members.find((candidate) => propertyName(candidate) === property);
  assert.ok(nested?.type, `${interfaceName}.${objectName}.${property} was not found`);
  return stringLiteralUnion(nested.type);
}

function typeAliasStringUnion(sourceFile, name) {
  return stringLiteralUnion(typeAliasDeclaration(sourceFile, name).type);
}

function stringLiteralUnion(node) {
  const members = ts.isUnionTypeNode(node) ? node.types : [node];
  return members.map((member) => {
    assert.ok(
      ts.isLiteralTypeNode(member) && ts.isStringLiteral(member.literal),
      "contract enum members must be string literal types"
    );
    return member.literal.text;
  });
}

function returnObjectPropertyNames(sourceFile, functionName) {
  const declaration = sourceFile.statements.find(
    (statement) => ts.isFunctionDeclaration(statement) && statement.name?.text === functionName
  );
  assert.ok(declaration?.body, `function ${functionName} was not found in ${sourceFile.fileName}`);
  let result;
  function visit(node) {
    if (!result && ts.isReturnStatement(node) && node.expression && ts.isObjectLiteralExpression(node.expression)) {
      result = sorted(node.expression.properties.map(propertyName));
      return;
    }
    ts.forEachChild(node, visit);
  }
  visit(declaration.body);
  assert.ok(result, `${functionName} must return an object literal`);
  return result;
}

function sorted(values) {
  return [...values].sort();
}
