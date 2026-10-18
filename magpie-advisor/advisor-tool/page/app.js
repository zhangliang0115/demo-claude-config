// Advisor 插件的设置页。
//
// 页面跑在 magpie 的沙箱里：连不了网络，只能读插件目录下的静态文件，
// 和通过 bridge 读写**本插件自己的 options**。所以：
//   - 可选模型来自 models.js（插件从 /v1/models 抄下来的完整条目）；
//   - 最近一次调用的结果来自 state.js（同样是插件写的）；
//   - 保存写进 magpie 的 options，插件下一次请求就读到。
//
// 模型选择器是自绘的：magpie 自己的那个是主窗口里的闭包组件，沙箱页面
// 拿不到（CSP 禁止 connect/frame，bridge 只给 options 和两种 read）。
// 这里用同一份 /v1/models 数据，按 provider 分组、可搜索、显示上下文窗口，
// 观感和 magpie 的选择器一致。模型名一律来自数据，不写死。
(() => {
  const $ = (id) => document.getElementById(id);
  const data = window.MAGPIE_ADVISOR_MODELS || { models: [] };
  const last = window.MAGPIE_ADVISOR_STATE || null;

  // entries 兼容两种历史格式：对象（现在）和纯 id 字符串（0.2.0 之前）。
  const entries = (Array.isArray(data.models) ? data.models : [])
    .map((m) => (typeof m === "string" ? { id: m } : m))
    .filter((m) => m && m.id);

  let selected = "";
  let query = "";

  // 这两个只是分组标题的兜底文案，不是模型名
  const ROUTING = "路由组";
  const OTHER = "其他";

  // providerOf 是分组用的名字：优先 /v1/models 里 magpie_label 带的 provider 名，
  // 其次 owned_by，都没有才退回 id 前缀。路由组单独一组。
  function providerOf(m) {
    if (m.group) return ROUTING;
    if (m.providerName) return m.providerName;
    if (m.provider) return m.provider;
    const i = String(m.id).indexOf("/");
    return i > 0 ? m.id.slice(0, i) : OTHER;
  }

  // shortName 去掉分组前缀，和 magpie 列表里显示的名字一致。
  function shortName(m) {
    const id = String(m.id);
    const i = id.indexOf("/");
    return i > 0 ? id.slice(i + 1) : id;
  }

  function contextLabel(n) {
    const v = Number(n);
    if (!v) return "";
    return v >= 1e6 ? v / 1e6 + "M" : v >= 1000 ? Math.round(v / 1000) + "k" : String(v);
  }

  function findEntry(id) {
    return entries.find((m) => m.id === id) || null;
  }

  function drawButton() {
    const btn = $("model-btn");
    const label = $("model-btn-label");
    if (!selected) {
      label.textContent = "（不设，最后用会话自己的模型）";
      label.classList.add("muted");
      btn.title = "";
      return;
    }
    label.classList.remove("muted");
    const m = findEntry(selected);
    label.textContent = m ? m.name || shortName(m) : selected;
    btn.title = m ? `${m.name || shortName(m)}\n${m.id}` : selected;
  }

  // rows 按搜索词过滤后按 provider 分组，顺序跟 /v1/models 给的一致。
  function grouped() {
    const q = query.trim().toLowerCase();
    const groups = new Map();
    for (const m of entries) {
      if (q) {
        const hay = `${m.id} ${m.name || ""} ${providerOf(m)}`.toLowerCase();
        if (!hay.includes(q)) continue;
      }
      const g = providerOf(m);
      if (!groups.has(g)) groups.set(g, []);
      groups.get(g).push(m);
    }
    return groups;
  }

  function drawList() {
    const list = $("model-list");
    list.replaceChildren();
    // matched 只数 /v1/models 里的真实模型：「不设」和「已保存但不在列表里」
    // 这两项是提示，不该算进「命中几个」。
    let matched = 0;

    const item = (m, label, sub, onPick) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "pop-item" + (selected === (m ? m.id : "") ? " on" : "");
      b.setAttribute("role", "option");
      b.setAttribute("aria-selected", String(selected === (m ? m.id : "")));
      const main = document.createElement("span");
      main.className = "pop-item-name";
      main.textContent = label;
      b.append(main);
      if (sub) {
        const s = document.createElement("span");
        s.className = "pop-item-sub";
        s.textContent = sub;
        b.append(s);
      }
      b.onclick = () => {
        onPick();
        close();
        drawButton();
      };
      list.append(b);
    };

    // 「不设」永远是第一项：这是默认行为，不该被搜索藏起来
    if (!query.trim()) item(null, "（不设，最后用会话自己的模型）", "", () => { selected = ""; });

    for (const [g, list0] of grouped()) {
      const h = document.createElement("div");
      h.className = "pop-group";
      h.textContent = g;
      list.append(h);
      for (const m of list0) {
        const bits = [];
        if (m.context) bits.push(contextLabel(m.context) + " 上下文");
        if (m.reasoning) bits.push("推理");
        // 分组标题已经写了「路由组」，条目上不再重复打标签
        item(m, m.name || shortName(m), bits.join(" · "), () => { selected = m.id; });
        matched++;
      }
    }

    // 配置里存着但当前列表里没有的模型：照样能选中，保存时不被悄悄清掉
    if (selected && !findEntry(selected)) {
      const h = document.createElement("div");
      h.className = "pop-group";
      h.textContent = "当前列表里没有";
      list.append(h);
      item({ id: selected }, selected, "已保存的配置", () => {});
    }

    if (!matched) {
      const p = document.createElement("p");
      p.className = "muted pop-empty";
      p.textContent = entries.length
        ? "没有匹配的模型。"
        : "还没有模型列表：打开一次 Claude Code 会话（或让模型调用一次 advisor），插件会把网关的模型列表写到这里。";
      list.append(p);
    }
    $("model-count").textContent = entries.length ? `${matched} / ${entries.length}` : "";
  }

  function open() {
    const pop = $("model-pop");
    pop.hidden = false;
    $("model-btn").setAttribute("aria-expanded", "true");
    query = "";
    $("model-search").value = "";
    drawList();
    $("model-search").focus();
  }

  function close() {
    $("model-pop").hidden = true;
    $("model-btn").setAttribute("aria-expanded", "false");
  }

  function showState(s) {
    const box = $("state");
    box.classList.remove("muted");
    if (!s) {
      box.textContent = "还没有调用记录。在 Claude Code 里让模型调用一次 advisor，这里就会显示用的哪个端点、哪个模型、耗时多久。";
      box.classList.add("muted");
      return;
    }
    const rows = [];
    rows.push(["结果", s.ok ? "成功" : "失败"]);
    if (s.endpoint) rows.push(["端点", s.endpoint]);
    if (s.model) rows.push(["实际模型", s.model]);
    if (s.declared) rows.push(["声明模型", s.declared]);
    if (s.why) rows.push(["选择原因", s.why]);
    if (s.ms != null) rows.push(["耗时", s.ms + " ms"]);
    if (s.chars != null) rows.push(["送入上下文", s.chars + " 字符"]);
    if (s.seen != null) rows.push(["对话条数", String(s.seen)]);
    if (s.captured != null) rows.push(["读到对话", s.captured ? "是" : "否"]);
    if (s.source) rows.push(["配置来源", s.source]);
    if (s.at) rows.push(["时间", new Date(s.at).toLocaleString()]);
    if (s.error) rows.push(["错误", s.error]);
    const dl = document.createElement("dl");
    for (const [k, v] of rows) {
      const dt = document.createElement("dt");
      dt.textContent = k;
      const dd = document.createElement("dd");
      dd.textContent = v;
      if (k === "错误") dd.className = "bad";
      dl.append(dt, dd);
    }
    box.replaceChildren(dl);
  }

  async function load() {
    const gw = data.gateway || "";
    $("gateway-hint").textContent = gw ? "网关地址：" + gw : "";
    let opts = {};
    try {
      opts = await magpie.options.get();
    } catch (e) {
      $("status").textContent = "读不到插件设置：" + e.message;
    }
    const eps = Array.isArray(opts.endpoints) ? opts.endpoints : [];
    $("endpoints").value = eps.map((e) => (typeof e === "string" ? e : e && e.url ? e.url : "")).filter(Boolean).join("\n");
    $("follow").checked = opts.follow !== false;
    $("budget").value = Number(opts.budget) > 0 ? Number(opts.budget) : 16000;
    selected = String(opts.model || "");
    drawButton();
    drawList();
    showState(last);
  }

  async function save() {
    const lines = $("endpoints").value.split("\n").map((s) => s.trim()).filter(Boolean);
    const budget = Number($("budget").value);
    const options = {
      endpoints: lines,
      model: selected,
      follow: $("follow").checked,
      budget: Number.isFinite(budget) && budget >= 1000 ? budget : 16000,
    };
    // 已有但没有在页面上暴露的键（models、timeout、key）原样保留
    try {
      const prev = await magpie.options.get();
      for (const k of ["models", "timeout", "key", "context"]) {
        if (prev && prev[k] !== undefined && options[k] === undefined) options[k] = prev[k];
      }
    } catch (e) {
      // 读不到就用页面上的值
    }
    $("save").disabled = true;
    try {
      await magpie.options.set(options);
      $("status").textContent = "已保存，下一次咨询生效。";
    } catch (e) {
      $("status").textContent = "保存失败：" + e.message;
    } finally {
      $("save").disabled = false;
    }
  }

  $("model-btn").onclick = (ev) => {
    ev.stopPropagation();
    if ($("model-pop").hidden) open(); else close();
  };
  $("model-search").oninput = (ev) => {
    query = ev.target.value;
    drawList();
  };
  $("model-pop").onclick = (ev) => ev.stopPropagation();
  document.addEventListener("mousedown", (ev) => {
    // 点在按钮上（包括里面的箭头图标）不算「点外面」，否则会先关再开
    if ($("model-pop").hidden || $("model-pop").contains(ev.target)) return;
    if (ev.target instanceof Element && ev.target.closest("#model-btn")) return;
    close();
  });
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && !$("model-pop").hidden) {
      close();
      $("model-btn").focus();
    }
  });

  $("save").onclick = save;
  $("follow").onchange = () => {
    $("model-btn").disabled = false; // 兜底模型在两种模式下都可用
  };
  magpie.ready.then(load, (e) => {
    $("status").textContent = "页面没能连上 magpie：" + e.message;
  });
})();
