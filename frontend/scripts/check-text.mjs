#!/usr/bin/env node
/**
 * Fail the build when a source file contains replacement characters or the common UTF-8/Windows-1252
 * mojibake sequences (P4-1).  Keeps every file under frontend/src valid UTF-8 without a BOM.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../src", import.meta.url));
const textDecoder = new TextDecoder("utf-8", { fatal: true });

const BAD = [
  { name: "U+FFFD replacement character", value: "\uFFFD" },
  { name: "mojibake middle dot (C2 B7)", value: "\u00C2\u00B7" },
  { name: "mojibake ellipsis (E2 20AC A6)", value: "\u00E2\u20AC\u00A6" },
];

function walk(directory) {
  const files = [];
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const full = join(directory, entry.name);
    if (entry.isDirectory()) files.push(...walk(full));
    else if (entry.isFile()) files.push(full);
  }
  return files;
}

const problems = [];
for (const file of walk(root)) {
  const bytes = readFileSync(file);
  const label = relative(root, file);
  if (bytes.length >= 3 && bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf) {
    problems.push(`${label}: starts with a UTF-8 BOM`);
    continue;
  }
  let text;
  try {
    text = textDecoder.decode(bytes);
  } catch {
    problems.push(`${label}: not valid UTF-8`);
    continue;
  }
  for (const bad of BAD) {
    if (text.includes(bad.value)) problems.push(`${label}: contains ${bad.name}`);
  }
}

if (problems.length > 0) {
  console.error("check:text failed:");
  for (const problem of problems) console.error(`  - ${problem}`);
  process.exit(1);
}

console.log(`check:text passed (${walk(root).length} files under frontend/src are clean UTF-8).`);
