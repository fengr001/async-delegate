# 子 agent 前端 JS 踩坑纪实（2026-05-05）

## 背景

两次派小弟改 Blade 前端模板（报价单版本管理 + 订单自动换算），均出现子 agent 输出 JS 代码有 bug 的情况。共 5 个独立 Bug 类型，均为「JS 逻辑正确但运行环境不对」。

## 实战复盘

### Bug 1：JS 在 `@push('scripts')` 中但没包 DOM ready

**子 agent 输出**
```javascript
@push('scripts')
<script>
$('[data-fa-action="save-version"]').click(function() { ... });
</script>
@endpush
```

**问题**：`@push('scripts')` 推送到 layout 底部，`<script>` 直接执行时 DOM 可能还没解析到按钮元素。jQuery 的 `$('...').click()` 直接绑定到空集。

**修复**：改为 + 委托绑定
```javascript
@push('scripts')
<script>
$(function() {
    $(document).on('click', '[data-fa-action="save-version"]', function() { ... });
});
</script>
@endpush
```

**教训**：子 agent 默认认为 script 在 body 底部运行时 DOM 已 ready，但 `@push('scripts')` 的加载时机不可控。

### Bug 2：版本按钮仅在 @if($isEdit) 中，JS 仍直接绑定

编辑模式按钮存在，创建模式不存在。JS 用直接绑定 `$('...').click(fn)`，创建模式下元素不存在 -> 静默失效。

（这解释了为什么「编辑页没反应，但是也不报错」）

### Bug 3：子 agent 加了 JS 但没加对应的 HTML 元素

子 agent 的 JS 引用了：
- `#version-save-modal` 
- `#version-note-input`
- `#version-result-modal`
- `#version-summary`
- `#confirm-save-version`

这些 modal HTML 元素在模板中不存在。`$('#version-save-modal').modal('show')` 不报错，但也不执行——因为 jQuery 的 `.modal()` 方法在空集上静默跳过。

**教训**：prompt 只说「加弹窗」，子 agent 理解成「加弹窗的 JS 逻辑」。必须明确说「加弹窗的 HTML 结构 + JS 逻辑」。

### Bug 4：$.post() 不带 _token -> 419 跳登录页

```javascript
$.post('/quotes/' + quoteId + '/snapshots', { note: note }, function(resp) { ... });
```

Laravel `VerifyCsrfToken` 中间件拦截 -> 返回 419 -> 浏览器自动重定向到 `/login`。看起来像「session 过期」，调试了 20 分钟才发现是 CSRF 问题。

**修复**：手动加上 `_token: $('meta[name="csrf-token"]').attr('content')`

### Bug 5：报价单创建页 500 — PHP 8 nullsafe 陷阱

```blade
{{ old('valid_until', $quote->valid_until?->format('Y-m-d') ?? '') }}
```

`$quote` 为 null 时，`$quote->valid_until` 抛 `Attempt to read property on null`。`?->` 只在 `valid_until` 字段为 null 时短路，**不保护 `$quote` 本身为 null**。

**修复**：`$quote?->valid_until?->format('Y-m-d')` — 把 `?->` 放在第一个访问的变量上。

## 提示词模板

派小弟改前端 Blade+JS 时，prompt 末尾必加：

> ## JS 约束（必须遵守）
> 1. 所有 JS 包在 $(function(){...}) 内
> 2. 事件绑定用 $(document).on('click', 'selector', fn)
> 3. 所有 JS 引用的元素 ID 在模板中必须有对应 HTML
> 4. $.post() 必须带 _token（或全局 $.ajaxSetup）
> 5. Blade 中 $var->prop 必须用 $var?->prop（PHP 8 nullsafe）
