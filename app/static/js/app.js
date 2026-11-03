/**
 * OLP'AI'26 - Web Console Client Application
 * Handles chat stream, markdown parsing, syntax highlighting, conversation management & UI ergonomics
 */

(() => {
  "use strict";

  // Application State
  const state = {
    activeId: null,
    budget: 2000,
    model: "OLP AI",
    conversations: [],
    commandHistory: [],
    historyIndex: 0,
  };

  // DOM Query Helpers
  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => document.querySelectorAll(selector);

  // SVG Icons Library for Dynamic Injection
  const ICONS = {
    copy: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>`,
    check: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>`,
    chat: `<svg class="chat-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>`,
    more: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="1.5"></circle><circle cx="19" cy="12" r="1.5"></circle><circle cx="5" cy="12" r="1.5"></circle></svg>`,
    edit: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>`,
    clear: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>`,
    trash: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>`,
    warning: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>`,
  };

  // Safe HTML Escaping
  const escapeHtml = (value) =>
    String(value).replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#039;",
    }[char]));

  // Toast Notification
  let toastTimer = null;
  function showToast(message, duration = 2200) {
    const toast = $("#toastBubble");
    if (!toast) return;
    $("#toastMessage").textContent = message;
    toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      toast.classList.remove("show");
    }, duration);
  }

  // API Client
  const api = async (url, options = {}) => {
    const { headers = {}, ...requestOptions } = options;
    const response = await fetch(url, {
      ...requestOptions,
      headers: { "Content-Type": "application/json", ...headers },
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(body.detail?.message || body.detail || `Yêu cầu thất bại (${response.status})`);
    }
    return body;
  };

  const setNotice = (message = "") => {
    const banner = $("#noticeBanner");
    if (banner) banner.textContent = message;
  };

  // Python Syntax Highlighter
  const pythonKeywords = new Set(
    "and as assert async await break case class continue def del elif else except finally for from global if import in is lambda match nonlocal not or pass raise return try while with yield print self cls".split(" ")
  );
  const pythonBuiltins = new Set(
    "abs all any bool dict enumerate filter float input int len list map max min open range set str sum tuple zip isinstance super type round sorted zip reversed next iter".split(" ")
  );
  const pythonConstants = new Set(["True", "False", "None"]);

  function highlightPython(source) {
    let html = "";
    let index = 0;
    while (index < source.length) {
      const char = source[index];

      // Whitespace
      if (/\s/.test(char)) {
        let end = index + 1;
        while (end < source.length && /\s/.test(source[end])) end += 1;
        html += escapeHtml(source.slice(index, end));
        index = end;
        continue;
      }

      // Single-line comment
      if (char === "#") {
        const end = source.indexOf("\n", index);
        const stop = end < 0 ? source.length : end;
        html += `<span class="py-comment">${escapeHtml(source.slice(index, stop))}</span>`;
        index = stop;
        continue;
      }

      // Strings (Triple & Single/Double quoted)
      if (char === "'" || char === '"') {
        const triple = source.slice(index, index + 3) === char.repeat(3);
        const quote = triple ? char.repeat(3) : char;
        let end = index + quote.length;
        while (end < source.length) {
          if (source[end] === "\\") {
            end += 2;
            continue;
          }
          if (source.slice(end, end + quote.length) === quote) {
            end += quote.length;
            break;
          }
          end += 1;
        }
        html += `<span class="py-string">${escapeHtml(source.slice(index, end))}</span>`;
        index = end;
        continue;
      }

      // Numbers
      const number = source.slice(index).match(/^(?:0[xX][0-9a-fA-F]+|0[bB][01]+|\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|\.\d+)/);
      if (number) {
        html += `<span class="py-number">${number[0]}</span>`;
        index += number[0].length;
        continue;
      }

      // Identifiers / Keywords / Functions
      const identifier = source.slice(index).match(/^[A-Za-z_]\w*/);
      if (identifier) {
        const word = identifier[0];
        const after = source.slice(index + word.length).match(/^\s*\(/);
        const className = pythonKeywords.has(word)
          ? "py-keyword"
          : pythonConstants.has(word)
          ? "py-constant"
          : pythonBuiltins.has(word)
          ? "py-builtin"
          : after
          ? "py-function"
          : "";
        html += className ? `<span class="${className}">${word}</span>` : escapeHtml(word);
        index += word.length;
        continue;
      }

      // Operators
      if (/[=+\-*\/%<>!&|^~:]/.test(char)) {
        html += `<span class="py-operator">${escapeHtml(char)}</span>`;
      } else {
        html += escapeHtml(char);
      }
      index += 1;
    }
    return html;
  }

  // Code Block Renderer
  function renderCodeBlock(language, source) {
    const rawLang = (language || "code").toLowerCase();
    const normalizedLang = rawLang === "py" ? "python" : rawLang;
    const renderedSource = normalizedLang === "python" ? highlightPython(source) : escapeHtml(source);

    return `
      <div class="code-shell-container">
        <div class="code-header-bar">
          <div class="code-window-dots">
            <span class="dot red"></span>
            <span class="dot yellow"></span>
            <span class="dot green"></span>
            <span class="code-lang-label">${escapeHtml(normalizedLang)}</span>
          </div>
          <button class="btn-copy-code" type="button" title="Sao chép mã nguồn">
            ${ICONS.copy}
            <span>Sao chép</span>
          </button>
        </div>
        <pre><code>${renderedSource}</code></pre>
      </div>`;
  }

  function looksLikePython(source) {
    const firstLine = source.split(/\r?\n/).find((line) => line.trim())?.trim() || "";
    return /^(?:from\s|import\s|def\s+\w+\s*\(|class\s+\w+|async\s+def\s|if\s+__name__|(?:for|while|if|elif|else|try|except|with)\b.*:|(?:print|return)\b|[A-Za-z_]\w*\s*=\s*|#)/.test(firstLine);
  }

  // Inline Markdown Parser
  function renderInlineMarkdown(text) {
    const inlineCode = [];
    let value = escapeHtml(text).replace(/`([^`\n]+)`/g, (_, source) => {
      const token = `@@INLINE_CODE_${inlineCode.length}@@`;
      inlineCode.push(`<code class="inline-code">${source}</code>`);
      return token;
    });

    value = value.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
    value = value.replace(/\*\*([^*\n]+)\*\*|__([^_\n]+)__/g, (_, bold, underscored) => `<strong>${bold || underscored}</strong>`);
    value = value.replace(/~~([^~\n]+)~~/g, "<del>$1</del>");
    value = value.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>");
    value = value.replace(/(^|[^\w])_([^_\n]+)_(?!\w)/g, "$1<em>$2</em>");
    value = value.replace(/\r?\n/g, "<br>");

    inlineCode.forEach((html, index) => {
      value = value.replace(`@@INLINE_CODE_${index}@@`, html);
    });
    return value;
  }

  // Full Markdown Parser
  function renderMarkdown(content) {
    if (!content.includes("```") && looksLikePython(content.trim())) {
      return renderCodeBlock("python", content.trim());
    }

    const codeBlocks = [];
    const fenced = content.replace(/```([a-zA-Z0-9_+-]*)[ \t]*\r?\n([\s\S]*?)(?:```|$)/g, (_, language, source) => {
      const token = `@@CODE_BLOCK_${codeBlocks.length}@@`;
      codeBlocks.push(renderCodeBlock(language || "code", source.replace(/^\n/, "").replace(/\n$/, "")));
      return `\n${token}\n`;
    });

    const lines = fenced.split(/\r?\n/);
    const html = [];
    let paragraph = [];
    let listType = null;

    const closeList = () => {
      if (listType) {
        html.push(`</${listType}>`);
        listType = null;
      }
    };
    const flushParagraph = () => {
      if (paragraph.length) {
        html.push(`<p>${renderInlineMarkdown(paragraph.join("\n"))}</p>`);
        paragraph = [];
      }
    };

    lines.forEach((line) => {
      const codeToken = line.trim().match(/^@@CODE_BLOCK_(\d+)@@$/);
      const heading = line.match(/^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$/);
      const unordered = line.match(/^\s*[-*+]\s+(.+)$/);
      const ordered = line.match(/^\s*\d+[.)]\s+(.+)$/);
      const quote = line.match(/^\s*>\s?(.*)$/);

      if (codeToken) {
        flushParagraph();
        closeList();
        html.push(codeBlocks[Number(codeToken[1])]);
      } else if (!line.trim()) {
        flushParagraph();
        closeList();
      } else if (heading) {
        flushParagraph();
        closeList();
        html.push(`<h${heading[1].length}>${renderInlineMarkdown(heading[2])}</h${heading[1].length}>`);
      } else if (unordered || ordered) {
        flushParagraph();
        const nextList = unordered ? "ul" : "ol";
        if (listType !== nextList) {
          closeList();
          listType = nextList;
          html.push(`<${listType}>`);
        }
        html.push(`<li>${renderInlineMarkdown((unordered || ordered)[1])}</li>`);
      } else if (quote) {
        flushParagraph();
        closeList();
        html.push(`<blockquote>${renderInlineMarkdown(quote[1])}</blockquote>`);
      } else {
        closeList();
        paragraph.push(line);
      }
    });

    flushParagraph();
    closeList();
    return html.join("");
  }

  // Copy Clipboard Handler
  async function copyTextToClipboard(text, triggerButton, labelEl = null, successText = "Đã chép") {
    try {
      await navigator.clipboard.writeText(text);
      if (triggerButton) {
        const originalHtml = triggerButton.innerHTML;
        triggerButton.classList.add("copied");
        triggerButton.innerHTML = `${ICONS.check} <span>${successText}</span>`;
        setTimeout(() => {
          triggerButton.classList.remove("copied");
          triggerButton.innerHTML = originalHtml;
        }, 1800);
      }
      showToast("Đã sao chép vào bộ nhớ tạm!");
    } catch (err) {
      console.error("Clipboard copy failed:", err);
      showToast("Không thể sao chép văn bản");
    }
  }

  // Bind All Copy Buttons
  function bindCopyButtons() {
    // 1. Code block copy buttons
    $$(".btn-copy-code").forEach((button) => {
      button.onclick = (e) => {
        e.stopPropagation();
        const codeElement = button.closest(".code-shell-container").querySelector("code");
        if (codeElement) {
          copyTextToClipboard(codeElement.textContent, button, null, "Đã chép!");
        }
      };
    });

    // 2. Global Message Copy Buttons
    $$(".btn-copy-message").forEach((button) => {
      button.onclick = (e) => {
        e.stopPropagation();
        const messageCard = button.closest(".message-bubble");
        const rawContent = messageCard?.dataset?.rawContent;
        if (rawContent) {
          copyTextToClipboard(rawContent, button, null, "Đã sao chép");
        } else {
          // Fallback to textContent of message body
          const body = messageCard?.querySelector(".message-body");
          if (body) copyTextToClipboard(body.innerText, button, null, "Đã sao chép");
        }
      };
    });

    // 3. User message copy buttons
    $$(".user-copy-btn").forEach((button) => {
      button.onclick = (e) => {
        e.stopPropagation();
        const messageBubble = button.closest(".message-bubble");
        const raw = messageBubble?.dataset?.rawContent || messageBubble?.querySelector(".message-body")?.innerText;
        if (raw) copyTextToClipboard(raw, button, null, "Đã chép");
      };
    });
  }

  // Auto-resize Textarea
  function autoResizeTextarea(textarea) {
    if (!textarea) return;
    textarea.style.height = "auto";
    const newHeight = Math.min(Math.max(textarea.scrollHeight, 24), 140);
    textarea.style.height = `${newHeight}px`;
  }

  // Close Conversation Context Menus
  function closeConversationMenus() {
    $$(".conversation-row.menu-open").forEach((row) => row.classList.remove("menu-open"));
  }

  // Update Token Meter Display
  function updateTokenMeter(usedTokens, budgetTokens) {
    const used = Math.max(0, Number(usedTokens) || 0);
    const total = Math.max(1, Number(budgetTokens) || state.budget);
    const percentage = Math.min(100, Math.round((used / total) * 100));

    $("#tokenUsageText").textContent = `${used.toLocaleString()} / ${total.toLocaleString()}`;
    const bar = $("#meterProgressBar");
    if (bar) {
      bar.style.width = `${percentage}%`;
      bar.classList.remove("warning", "danger");
      if (percentage >= 85) {
        bar.classList.add("danger");
      } else if (percentage >= 60) {
        bar.classList.add("warning");
      }
    }
  }

  // Render Conversation Sidebar List
  function renderConversations() {
    const list = $("#conversationList");
    const countBadge = $("#conversationCountBadge");
    if (countBadge) countBadge.textContent = state.conversations.length;

    if (!state.conversations.length) {
      list.innerHTML = `
        <div class="empty-chats">
          Chưa có cuộc trò chuyện nào.<br>Bấm <strong>+ Cuộc trò chuyện mới</strong> để bắt đầu.
        </div>`;
      return;
    }

    list.innerHTML = state.conversations
      .map((item) => {
        const isActive = item.id === state.activeId;
        return `
        <div class="conversation-row ${isActive ? "active" : ""}" data-row-id="${escapeHtml(item.id)}">
          <button class="conversation-item-btn" data-id="${escapeHtml(item.id)}" title="${escapeHtml(item.title)}">
            <div class="item-title-row">
              ${ICONS.chat}
              <span class="conversation-title">${escapeHtml(item.title)}</span>
            </div>
            <div class="conversation-meta-row">
              <span>${item.used_tokens} / ${item.budget_tokens} tokens</span>
            </div>
          </button>
          <button class="menu-trigger-btn" data-menu-id="${escapeHtml(item.id)}" title="Thao tác" aria-label="Thao tác">
            ${ICONS.more}
          </button>
          <div class="conversation-menu-popover">
            <button class="menu-action-item" type="button" data-action="rename" data-id="${escapeHtml(item.id)}" data-title="${escapeHtml(item.title)}">
              ${ICONS.edit}
              <span>Đổi tên</span>
            </button>
            <button class="menu-action-item" type="button" data-action="clear" data-id="${escapeHtml(item.id)}">
              ${ICONS.clear}
              <span>Xóa tin nhắn</span>
            </button>
            <button class="menu-action-item danger-action" type="button" data-action="delete" data-id="${escapeHtml(item.id)}">
              ${ICONS.trash}
              <span>Xóa hẳn</span>
            </button>
          </div>
        </div>`;
      })
      .join("");

    // Bind item click
    list.querySelectorAll(".conversation-item-btn").forEach((button) => {
      button.addEventListener("click", () => selectConversation(button.dataset.id));
    });

    // Bind 3-dot menu trigger
    list.querySelectorAll(".menu-trigger-btn").forEach((button) => {
      button.addEventListener("click", (event) => {
        event.stopPropagation();
        const row = button.closest(".conversation-row");
        const wasOpen = row.classList.contains("menu-open");
        closeConversationMenus();
        if (!wasOpen) row.classList.add("menu-open");
      });
    });

    // Bind Actions: Rename, Clear, Delete
    list.querySelectorAll("[data-action='rename']").forEach((btn) => {
      btn.addEventListener("click", () => renameConversation(btn.dataset.id, btn.dataset.title));
    });
    list.querySelectorAll("[data-action='clear']").forEach((btn) => {
      btn.addEventListener("click", () => clearConversation(btn.dataset.id));
    });
    list.querySelectorAll("[data-action='delete']").forEach((btn) => {
      btn.addEventListener("click", () => deleteConversation(btn.dataset.id));
    });
  }

  // Welcome Screen HTML
  function getWelcomeScreenHTML() {
    return `
      <div class="welcome-screen">
        <div class="welcome-logo-emblem">
          <img src="/static/assets/logo.jpg" alt="OLP'AI'26 Logo">
        </div>
        <div class="welcome-headings">
          <h2>Chào mừng bạn đến với OLP'AI'26</h2>
          <p>Trợ lý AI chuyên biệt hỗ trợ tư vấn thuật toán, lập trình thi đấu và tối ưu hoá mã nguồn cho kì thi OLP Tin học & AI 2026.</p>
        </div>
        <div class="suggestion-chips-grid">
          <button class="suggestion-chip-btn" data-prompt="Bạn hãy giải thích thuật toán Dijkstra và viết code mẫu tối ưu bằng Python?">
            <span class="chip-icon">⚡</span>
            <div><strong>Thuật toán Dijkstra</strong><br>Code mẫu cấu trúc Heap tối ưu O((V+E)logV)</div>
          </button>
          <button class="suggestion-chip-btn" data-prompt="Hãy phân tích hướng tiếp cận bài toán Quy hoạch động Knapsack và code Python">
            <span class="chip-icon">💡</span>
            <div><strong>Quy hoạch động Knapsack</strong><br>Tối ưu không gian O(W) và truy vết kết quả</div>
          </button>
          <button class="suggestion-chip-btn" data-prompt="Hãy xây dựng kiến trúc mạng Transformer cơ bản với PyTorch cho bài toán NLP">
            <span class="chip-icon">🧠</span>
            <div><strong>PyTorch Transformer</strong><br>Triển khai Self-Attention và Encoder layer</div>
          </button>
          <button class="suggestion-chip-btn" data-prompt="Cách tối ưu hoá thời gian chạy (Fast I/O) và tránh lỗi TLE trong Python khi thi OLP?">
            <span class="chip-icon">🔍</span>
            <div><strong>Tối ưu Fast I/O Python</strong><br>Tránh lỗi TLE, tối ưu bộ nhớ bộ nhớ đệm</div>
          </button>
        </div>
      </div>`;
  }

  // Render Full Active Conversation
  function renderConversation(conversation) {
    state.activeId = conversation.id;
    state.commandHistory = conversation.messages
      .filter((msg) => msg.role === "user")
      .map((msg) => msg.content);
    state.historyIndex = state.commandHistory.length;

    $("#topbarChatTitle").textContent = conversation.title;
    $("#topbarChatId").textContent = `ID: ${conversation.id}`;

    updateTokenMeter(conversation.used_tokens, conversation.budget_tokens);

    const stream = $("#messagesStream");
    if (!conversation.messages || conversation.messages.length === 0) {
      stream.innerHTML = getWelcomeScreenHTML();
      bindSuggestionChips();
    } else {
      stream.innerHTML = conversation.messages
        .map((message) => {
          if (message.role === "user") {
            return `
              <div class="message-bubble user" data-raw-content="${escapeHtml(message.content)}">
                <div class="user-card">
                  <div class="message-body">${escapeHtml(message.content)}</div>
                  <div class="user-footer-row">
                    <button class="user-copy-btn" type="button" title="Sao chép">
                      ${ICONS.copy}
                      <span>Chép</span>
                    </button>
                  </div>
                </div>
              </div>`;
          } else {
            return `
              <div class="message-bubble model" data-raw-content="${escapeHtml(message.content)}">
                <div class="model-card">
                  <div class="model-header-row">
                    <div class="model-author-info">
                      <div class="model-avatar-badge">
                        <img src="/static/assets/logo.jpg" alt="OLP'AI">
                      </div>
                      <span class="model-title-text">OLP'AI'26</span>
                      <span class="model-badge-tag">Assistant</span>
                    </div>
                    <button class="btn-copy-message" type="button" title="Sao chép toàn bộ phản hồi">
                      ${ICONS.copy}
                      <span>Sao chép</span>
                    </button>
                  </div>
                  <div class="message-body">${renderMarkdown(message.content)}</div>
                  ${
                    message.truncated
                      ? `<div class="truncated-note-card">${ICONS.warning}<span>Phản hồi đã bị ngắt do đạt ngân sách 2.000 token của cuộc trò chuyện.</span></div>`
                      : ""
                  }
                </div>
              </div>`;
          }
        })
        .join("");
    }

    // Scroll to bottom
    const container = $("#chatContainer");
    if (container) container.scrollTop = container.scrollHeight;

    bindCopyButtons();
    renderConversations();
  }

  // Bind Suggestion Chips
  function bindSuggestionChips() {
    $$(".suggestion-chip-btn").forEach((chip) => {
      chip.onclick = () => {
        const prompt = chip.dataset.prompt;
        const input = $("#messageInput");
        if (input && prompt) {
          input.value = prompt;
          autoResizeTextarea(input);
          $("#chatForm").requestSubmit();
        }
      };
    });
  }

  // Append Pending Message (Optimistic UI)
  function appendPendingMessage(role, content, pendingId) {
    const stream = $("#messagesStream");
    stream.querySelector(".welcome-screen")?.remove();

    if (role === "user") {
      stream.insertAdjacentHTML(
        "beforeend",
        `<div class="message-bubble user pending" data-pending-id="${pendingId}" data-raw-content="${escapeHtml(content)}">
          <div class="user-card">
            <div class="message-body">${escapeHtml(content)}</div>
          </div>
        </div>`
      );
    } else {
      stream.insertAdjacentHTML(
        "beforeend",
        `<div class="message-bubble model pending" data-pending-id="${pendingId}">
          <div class="model-card">
            <div class="model-header-row">
              <div class="model-author-info">
                <div class="model-avatar-badge">
                  <img src="/static/assets/logo.jpg" alt="OLP'AI">
                </div>
                <span class="model-title-text">OLP'AI'26</span>
                <span class="model-badge-tag">Thinking</span>
              </div>
            </div>
            <div class="message-body">${renderMarkdown(content)}</div>
          </div>
        </div>`
      );
    }

    const container = $("#chatContainer");
    if (container) container.scrollTop = container.scrollHeight;
  }

  function removePendingMessage(pendingId) {
    document.querySelector(`[data-pending-id="${pendingId}"]`)?.remove();
  }

  // Conversation Operations
  async function refreshConversations() {
    try {
      state.conversations = await api("/api/v1/conversations");
      renderConversations();
    } catch (error) {
      console.error("Failed to load conversations:", error);
    }
  }

  async function selectConversation(id) {
    try {
      setNotice("");
      const conversation = await api(`/api/v1/conversations/${id}`);
      renderConversation(conversation);
      // Close mobile sidebar if open
      $("#sidebar")?.classList.remove("open");
    } catch (error) {
      setNotice(error.message);
    }
  }

  async function newConversation() {
    try {
      setNotice("");
      const conversation = await api("/api/v1/conversations", {
        method: "POST",
        body: JSON.stringify({ title: "Cuộc trò chuyện mới" }),
      });
      await refreshConversations();
      renderConversation(conversation);
      $("#messageInput")?.focus();
      $("#sidebar")?.classList.remove("open");
    } catch (error) {
      setNotice(error.message);
    }
  }

  async function renameConversation(id, currentTitle) {
    closeConversationMenus();
    const title = prompt("Nhập tiêu đề mới cho cuộc trò chuyện:", currentTitle);
    if (title === null || !title.trim()) return;
    try {
      const conversation = await api(`/api/v1/conversations/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ title: title.trim() }),
      });
      if (state.activeId === id) renderConversation(conversation);
      await refreshConversations();
      showToast("Đã đổi tên cuộc trò chuyện!");
    } catch (error) {
      setNotice(error.message);
    }
  }

  async function clearConversation(id) {
    closeConversationMenus();
    if (!confirm("Bạn có chắc chắn muốn xóa tất cả tin nhắn trong đoạn chat này? Thao tác này sẽ reset lại ngân sách token.")) return;
    try {
      const conversation = await api(`/api/v1/conversations/${id}/messages`, { method: "DELETE" });
      if (state.activeId === id) renderConversation(conversation);
      await refreshConversations();
      showToast("Đã xóa tin nhắn cuộc trò chuyện!");
    } catch (error) {
      setNotice(error.message);
    }
  }

  async function deleteConversation(id) {
    closeConversationMenus();
    if (!confirm("Bạn có chắc chắn muốn xóa vĩnh viễn cuộc trò chuyện này?")) return;
    try {
      await api(`/api/v1/conversations/${id}`, { method: "DELETE" });
      if (state.activeId === id) {
        state.activeId = null;
        state.commandHistory = [];
        state.historyIndex = 0;
        $("#topbarChatTitle").textContent = "Cuộc trò chuyện mới";
        $("#topbarChatId").textContent = "Chưa chọn cuộc trò chuyện";
        $("#messagesStream").innerHTML = getWelcomeScreenHTML();
        bindSuggestionChips();
        updateTokenMeter(0, state.budget);
      }
      await refreshConversations();
      showToast("Đã xóa cuộc trò chuyện!");
    } catch (error) {
      setNotice(error.message);
    }
  }

  // Previous Command History
  function usePreviousCommand() {
    if (!state.commandHistory.length) return;
    state.historyIndex = Math.max(0, state.historyIndex - 1);
    const input = $("#messageInput");
    input.value = state.commandHistory[state.historyIndex];
    autoResizeTextarea(input);
    input.focus();
    input.setSelectionRange(input.value.length, input.value.length);
  }

  // Form Submission
  $("#chatForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = $("#messageInput");
    const sendBtn = $("#sendButton");
    const message = input.value.trim();
    if (!message) return;

    sendBtn.disabled = true;
    setNotice("");

    const pendingUserId = `pending-user-${Date.now()}`;
    const pendingAssistantId = `pending-assistant-${Date.now()}`;

    appendPendingMessage("user", message, pendingUserId);
    appendPendingMessage("model", "OLP'AI'26 đang suy nghĩ và tính toán lời giải...", pendingAssistantId);

    // Reset textarea
    input.value = "";
    autoResizeTextarea(input);

    try {
      const result = await api("/api/v1/chat", {
        method: "POST",
        body: JSON.stringify({
          conversation_id: state.activeId,
          message,
        }),
      });

      renderConversation(result.conversation);
      await refreshConversations();
    } catch (error) {
      removePendingMessage(pendingUserId);
      removePendingMessage(pendingAssistantId);
      setNotice(error.message || "Lỗi khi xử lý tin nhắn");
      showToast("Gặp sự cố: " + (error.message || "Lỗi mạng"), 3500);
    } finally {
      sendBtn.disabled = false;
      input.focus();
    }
  });

  // Textarea Events & Keyboard Navigation
  const messageInput = $("#messageInput");
  messageInput.addEventListener("input", () => {
    autoResizeTextarea(messageInput);
  });

  messageInput.addEventListener("keydown", (event) => {
    if (event.key === "ArrowUp" && !event.shiftKey && !event.target.value.trim()) {
      event.preventDefault();
      usePreviousCommand();
      return;
    }
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      $("#chatForm").requestSubmit();
    }
  });

  $("#historyUpBtn")?.addEventListener("click", usePreviousCommand);
  $("#newChatBtn")?.addEventListener("click", newConversation);

  // Close menus on outside click
  document.addEventListener("click", closeConversationMenus);

  // Mobile Drawer Toggle
  $("#mobileMenuToggle")?.addEventListener("click", () => {
    $("#sidebar")?.classList.add("open");
  });
  $("#mobileCloseBtn")?.addEventListener("click", () => {
    $("#sidebar")?.classList.remove("open");
  });

  // Settings Modal Handlers
  const settingsDialog = $("#settingsDialog");
  $("#openSettingsBtn")?.addEventListener("click", (e) => {
    e.preventDefault();
    settingsDialog?.showModal();
    $("#settingsNotice").textContent = "";
  });
  $("#closeSettingsBtn")?.addEventListener("click", () => {
    settingsDialog?.close();
  });
  $("#cancelSettingsBtn")?.addEventListener("click", () => {
    settingsDialog?.close();
  });

  $("#settingsForm")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const notice = $("#settingsNotice");
    try {
      const result = await api("/api/v1/settings/api-key", {
        method: "PUT",
        headers: { "X-API-Key-Password": $("#updatePassword").value },
        body: JSON.stringify({ api_key: $("#apiKey").value }),
      });
      notice.style.color = "var(--color-brand-primary)";
      notice.textContent = `Đã cập nhật: ${result.masked_api_key}`;
      $("#apiKey").value = "";
      $("#updatePassword").value = "";
      showToast("Đã cập nhật Gemini API Key thành công!");
      setTimeout(() => settingsDialog.close(), 1200);
    } catch (error) {
      notice.style.color = "var(--color-brand-danger)";
      notice.textContent = error.message;
    }
  });

  // System Initialization Boot
  async function boot() {
    try {
      const config = await api("/api/v1/config");
      state.budget = config.budget_tokens;
      state.model = config.model;

      $("#topbarModelName").textContent = config.model;
      updateTokenMeter(0, state.budget);

      await refreshConversations();

      // If conversations exist, select the first one, or render welcome screen
      if (state.conversations.length > 0) {
        await selectConversation(state.conversations[0].id);
      } else {
        $("#messagesStream").innerHTML = getWelcomeScreenHTML();
        bindSuggestionChips();
      }

      $("#statusText").textContent = "Connected";
      $("#statusDot").classList.remove("error");
    } catch (error) {
      console.error("Boot failure:", error);
      $("#statusText").textContent = "Offline";
      $("#statusDot").classList.add("error");
      setNotice("Không thể kết nối đến máy chủ OLP AI");
      $("#messagesStream").innerHTML = getWelcomeScreenHTML();
      bindSuggestionChips();
    }
  }

  // Start Application
  boot();
})();

