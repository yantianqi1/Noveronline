import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

const webRoot = path.resolve(import.meta.dirname, "..");

async function source(relativePath) {
  return readFile(path.join(webRoot, relativePath), "utf8");
}

test("registration API posts the onboarding payload and requires an HttpOnly session cookie", async () => {
  const client = await source("lib/registration-api.ts");

  assert.match(client, /\/v1\/auth\/signup/);
  assert.match(client, /method:\s*"POST"/);
  assert.match(client, /"Content-Type":\s*"application\/json"/);
  assert.match(client, /display_name:\s*input\.displayName/);
  assert.match(client, /email:\s*input\.email/);
  assert.match(client, /password:\s*input\.password/);
  assert.match(client, /project_title:\s*input\.projectTitle/);
  assert.match(client, /"X-Mirofish-Recovery-Client":\s*input\.clientProof\.trim\(\)/);
  assert.match(client, /response\.headers\.get\("set-cookie"\)/);
  assert.match(client, /startsWith\("mirofish_session="\)/);
  assert.match(client, /cookie\.http_only\s*&&\s*cookie\.max_age\s*>\s*0/);
  assert.match(client, /active_tenants:\s*activeTenants/);
  assert.match(client, /active_projects:\s*activeProjects/);
  assert.doesNotMatch(client, /X-User-Id|X-Tenant-Id|console\.|localStorage|sessionStorage/);
});

test("signup action validates confirmation, installs the cookie, and enters the first project", async () => {
  const page = await source("app/signup/page.tsx");

  for (const field of ["display_name", "email", "password", "confirmation", "project_title"]) {
    assert.match(page, new RegExp(`formData, \\"${field}\\"`));
  }
  assert.match(page, /input\.confirmation\s*!==\s*input\.password/);
  assert.match(page, /createRecoveryClientProof\(await headers\(\)\)/);
  assert.match(page, /registerAccount\(\{\s*displayName,\s*email,\s*password,\s*projectTitle,\s*clientProof\s*\}\)/s);
  assert.match(page, /const project = result\.active_projects\[0\]/);
  assert.match(page, /cookieStore\.set\("mirofish_session",\s*result\.session_cookie\.value/);
  assert.match(page, /httpOnly:\s*result\.session_cookie\.http_only/);
  assert.match(page, /sameSite:\s*result\.session_cookie\.same_site/);
  assert.match(page, /redirect\(workspacePathForProject\(result\.active_tenants,\s*project,\s*"overview"\)\)/);
  assert.match(page, /个人工作区/);
  assert.match(page, /href="\/login"/);
  assert.doesNotMatch(page, /invitations\/accept|X-User-Id|X-Tenant-Id|console\./);
});

test("signup form has accessible fields, inline failures, password toggles, and pending feedback", async () => {
  const form = await source("components/signup-form.tsx");

  assert.match(form, /useActionState\(action,\s*INITIAL_STATE\)/);
  assert.match(form, /useFormStatus\(\)/);
  assert.match(form, /role="alert"/);
  assert.match(form, /aria-invalid=/);
  assert.match(form, /htmlFor="signup-display-name"/);
  assert.match(form, /htmlFor="signup-email"/);
  assert.match(form, /id="signup-password"/);
  assert.match(form, /id="signup-confirmation"/);
  assert.match(form, /htmlFor="signup-project-title"/);
  assert.match(form, /autoComplete="email"/);
  assert.match(form, /autoComplete="new-password"/);
  assert.match(form, /maxLength=\{72\}/);
  assert.doesNotMatch(form, /minLength=\{12\}/);
  assert.match(form, /disabled=\{pending\}/);
  assert.match(form, /正在创建账号/);
  assert.match(form, /aria-label=\{visible \? `隐藏\$\{label\}` : `显示\$\{label\}`\}/);
  const page = await source("app/signup/page.tsx");
  assert.match(page, /Array\.from\(input\.displayName\)\.length/);
  assert.match(page, /Array\.from\(input\.projectTitle\)\.length/);
  assert.match(page, /new TextEncoder\(\)\.encode\(input\.password\)\.length/);
});

test("account entry and project navigation present workspace language without single-workspace clutter", async () => {
  const [login, nav] = await Promise.all([
    source("app/login/page.tsx"),
    source("components/project-nav.tsx"),
  ]);

  assert.match(login, /还没有账号？\s*<Link href="\/signup">免费注册<\/Link>/);
  assert.doesNotMatch(login, /申请加入|invitations\/accept">申请加入/);
  assert.match(nav, /const hasMultipleWorkspaces = activeTenants\.length > 1/);
  assert.match(nav, /hasMultipleWorkspaces\s*\?\s*\(/);
  assert.match(nav, /zh="我的工作区"/);
  assert.match(nav, /zh="切换工作区"/);
  assert.match(nav, /routeTenantProjects\.length > 1/);
  assert.match(nav, /zh="切换项目"/);
  assert.match(nav, /zh="撤销工作区会话"/);
  assert.doesNotMatch(nav, /租户/);
});

test("user-visible collaboration and configuration surfaces use workspace terminology", async () => {
  const surfaces = await Promise.all([
    source("components/members-workspace.tsx"),
    source("components/asset-library-shell.tsx"),
    source("components/llm-facility-shell.tsx"),
    source("components/llm-quota-admin-shell.tsx"),
    source("components/writer-product-workspace.tsx"),
  ]);
  const visibleTenantTerms = /租户|Tenant members|Tenant Settings|Tenant defaults|No tenant default|tenant owner\/admin|Module → Project → Tenant|>tenant</;

  for (const surface of surfaces) {
    assert.doesNotMatch(surface, visibleTenantTerms);
  }
  assert.match(surfaces.join("\n"), /工作区成员|工作区设置|工作区默认绑定|Workspace members|Workspace Settings|Workspace defaults/);
});
