// 排查用的日志：一行一个 JSON，写到 ~/.config/magpie/advisor.log。
//
// 为什么不只写 stderr：magpie 会把插件的 stderr 收进它自己的日志，
// 但桌面版从 Finder 启动时那份日志用户不容易找到。写一个固定路径的文件，
// 出问题时能直接打开看。
//
// 只记关键信息（时间、端点、模型、候选原因、耗时、字符数、错误），
// 不记对话内容，也不记 key。

import { appendFileSync, mkdirSync, renameSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { configDir } from "./config.js";

const MAX_BYTES = 1 << 20; // 1MB，超过就轮转一份 .1

// logFile 跟随 magpie 的配置目录：钩子给 ctx.directory，工具没有就按惯例推。
export function logFile(fromCtx) {
  return join(configDir(fromCtx), "advisor.log");
}

let rotated = false;

function rotate(file) {
  if (rotated) return;
  rotated = true;
  try {
    if (statSync(file).size > MAX_BYTES) renameSync(file, file + ".1");
  } catch (e) {
    // 文件还不存在，或没权限：下次再说
  }
}

// log 写一条事件。写失败不影响咨询本身。
export function log(event, fromCtx) {
  const line = JSON.stringify({ at: new Date().toISOString(), ...event }) + "\n";
  try {
    const file = logFile(fromCtx);
    mkdirSync(dirname(file), { recursive: true });
    rotate(file);
    appendFileSync(file, line, { mode: 0o600 });
  } catch (e) {
    // 日志写不出去时退回 stderr，magpie 会以 "plugin: …" 收进它自己的日志
  }
  try {
    process.stderr.write("[advisor] " + line);
  } catch (e) {
    // 同上
  }
}
