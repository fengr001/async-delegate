# 子 agent JS 常见质量缺陷与修复模式

本文件记录了子 agent（特别是 deepseek/minimax 模型）在生成 Blade 内联 JS 时常犯的错误，以及对应的修复模式。

## 常见的 5 种 JS 缺陷

### 1. 🔴 JS 脱离 DOM ready 包装

**症状**：页面加载后按钮点不动，事件绑不上。`console` 无报错但 `$('button').click()` 不触发。

**根因**：子 agent 在 `@push('scripts')` 内写了 JS 代码，但放在 `$(function(){})` / `$(document).ready()` 外面。脚本加载时 DOM 可能未就绪，直接绑定的 click handler 找不到元素。

**修复**：整个 script 块包进 `$(function(){ ... })` 内。

```javascript
// ❌ 错误：离开 DOM ready 包装
var quoteId = {{ $quote->id }};
$('[data-fa-action="save-version"]').click(function() { ... });
$('[data-fa-action="version-history"]').click(function() { ... });

// ✅ 正确：包进 DOM ready
$(function() {
    var quoteId = {{ $quote?->id ?? 'null' }};
    $(document).on('click', '[data-fa-action="save-version"]', function() { ... });
    $(document).on('click', '[data-fa-action="version-history"]', function() { ... });
});
```

### 2. 🔴 直接绑定而非委托

**症状**：页面上已有的元素能绑事件，但动态创建的元素（如用户新增的行、弹窗内的按钮）点不动。

**根因**：用 `$('.foo').click(fn)` 直接绑 — 只在绑定当时扫描一次 DOM。动态加入的后代元素不会被绑定。

**修复**：一律用 `$(document).on('click', '.foo', fn)` 委托模式。

```javascript
// ❌ 错误：直接绑定
$('.remove-item').click(function() { ... });

// ✅ 正确：委托绑定
$(document).on('click', '.remove-item', function() { ... });
```

**例外**：`$(function(){})` 内的直接绑定是安全的——因为有 DOM ready 保证元素已存在。但动态新增的行/弹窗仍不生效。所以**默认总用委托**。

### 3. 🟡 引用不存在的 HTML 元素

**症状**：JS 不报错但功能不工作 — 因为引用的 modal/div/input 在 Blade 中不存在。

**根因**：子 agent 在 JS 代码中引用了如 `#version-save-modal`、`#version-note-input` 等元素，但忘记在 HTML 中加上对应的 modal 模板。

**修复**：JS 中引用的**每一个 DOM ID**，确认 Blade 模板内有对应的 `<div>`、`<input>`、`<button>` 等元素。常见遗漏：
- Modal 壳：`<div class="modal fade" id="xxx-modal">`
- 输入框：`<input id="xxx-input">`
- 显示区：`<div id="xxx-summary">`

**防御**：写 prompt 时加一条「JS 中引用的所有 DOM ID 必须在 Blade 中有对应元素」。

### 4. 🟡 POST 请求未带 CSRF token

**症状**：`$.post()` 返回 419，页面跳转到登录页。Laravel 的 VerifyCsrfToken 中间件拦截了无 token 的 POST。

**根因**：`$.post('/api/endpoint', { data }, fn)` 默认不带 `_token` 参数。Laravel 需要 `_token` 或 `X-CSRF-TOKEN` 头。

**修复**：每个 `$.post` 调用加上 `_token`：

```javascript
var csrfToken = $('meta[name="csrf-token"]').attr('content');
$.post('/url', { data: data, _token: csrfToken }, function(resp) { ... });
```

或在全局 AJAX 配置中设置（如果布局有 meta csrf-token 标签）：

```javascript
$.ajaxSetup({
    headers: { 'X-CSRF-TOKEN': $('meta[name="csrf-token"]').attr('content') }
});
```

### 5. 🟡 Blade 变量直接在 JS 中取值未做 nullsafe

**症状**：编辑模式正常，创建模式报 `Attempt to read property on null`。

**根因**：JS 中 `var id = {{ $quote->id }};` 在创建模式下 `$quote` 是 null，PHP 报错。

**修复**：一定要用 nullsafe 操作符 `?->`：

```javascript
// ❌ 创建模式崩溃
var quoteId = {{ $quote->id }};

// ✅ 创建模式安全
var quoteId = {{ $quote?->id ?? 'null' }};
```

## 2026-05-05 实战案例

派小弟开发报价单版本快照功能（controller+model+routes+blade+JS），返回结果包含了上述全部 5 种缺陷：

| # | 缺陷 | 发现方式 | 修复耗时 |
|---|------|---------|---------|
| 1 | JS 在 DOM ready 外 | 按钮点不动 | 5 min |
| 2 | 直接绑定非委托 | 动态内容不响应 | 2 min |
| 3 | 缺失 modal HTML | 页面无弹窗 | 3 min |
| 4 | POST 缺 _token | 提交跳登录页 | 1 min |
| 5 | Blade 变量无 nullsafe | 创建页 500 | 2 min |

**教训**：子 agent 生成的大段 JS 需要强制要求它在确认了 Blade 模板后再写 JS，或者把上述 5 条加入 prompt 的系统约束中。
