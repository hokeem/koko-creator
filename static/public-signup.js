(() => {
  const form = document.querySelector("#auth-form");
  if (!form) return;

  const originalSetAuthMode = setAuthMode;
  setAuthMode = function () {
    originalSetAuthMode("login");
    authMode = "kwai_link";
    form.noValidate = true;
    const portuguese = lang !== "zh";
    const input = document.querySelector("#auth-phone");
    input.name = "kwai_url";
    input.type = "text";
    input.inputMode = "url";
    input.autocomplete = "url";
    input.placeholder = portuguese ? "Cole aqui o link do seu perfil Kwai" : "粘贴 Kwai 个人主页链接";
    input.required = true;
    const password = document.querySelector("#auth-password");
    if (password) {
      password.hidden = true;
      password.required = false;
      password.disabled = true;
    }
    document.querySelector("#auth-guide").classList.remove("active");
    document.querySelector("#auth-guide").hidden = true;
    document.querySelector(".auth-switch").hidden = true;
    document.querySelector("#auth-back").classList.remove("active");
    document.querySelector("#auth-title").textContent = portuguese ? "Copie o link do seu perfil Kwai" : "复制 Kwai 个人主页链接";
    document.querySelector("#auth-submit").textContent = portuguese ? "Continuar com meu perfil" : "使用主页链接进入";
    const hint = document.querySelector("#auth-login-hint");
    hint.hidden = false;
    hint.innerHTML = portuguese
      ? "No Kwai, abra seu perfil e toque em <strong>Compartilhar → Copiar link</strong>."
      : "打开 Kwai 个人主页，点击<strong>分享 → 复制链接</strong>。";
    input.before(hint);
    let guide = document.querySelector("#kwai-copy-guide");
    if (!guide) {
      guide = document.createElement("a");
      guide.id = "kwai-copy-guide";
      guide.className = "kwai-copy-guide";
      guide.href = "/static/kwai-copy-profile-guide.png";
      guide.target = "_blank";
      guide.rel = "noopener";
      guide.setAttribute("aria-label", portuguese ? "Ver imagem completa: toque em Compartilhar e Copiar link no Kwai" : "查看完整示意图：在 Kwai 点击分享并复制链接");
      guide.innerHTML = '<img src="/static/kwai-copy-link-steps.png" alt="Kwai: Compartilhar, Copy Link e Cancel"><span></span>';
      input.before(guide);
    }
    guide.querySelector("span").textContent = portuguese ? "Toque na imagem para ampliar" : "点击图片查看大图";
    document.querySelector("#auth-link-note")?.remove();
    document.querySelectorAll('.landing [data-auth-open="login"]').forEach(button => {
      button.textContent = portuguese ? "Entrar com meu perfil Kwai" : "使用 Kwai 主页进入";
    });
  };

  form.addEventListener("submit", async event => {
    if (authMode !== "kwai_link") return;
    event.preventDefault();
    event.stopImmediatePropagation();
    const button = document.querySelector("#auth-submit");
    if (button.disabled) return;
    const kwai_url = document.querySelector("#auth-phone").value.trim();
    const portuguese = lang !== "zh";
    if (!kwai_url) {
      setAuthStatus(portuguese ? "Cole o link do seu perfil no Kwai para continuar." : "请粘贴 Kwai 主页链接后继续。", "error");
      return;
    }
    setButtonBusy(button, true, portuguese ? "Identificando seu perfil..." : "正在识别主页...");
    setAuthStatus(portuguese ? "Preparando seu espaço na Koko..." : "正在准备你的 Koko 页面...", "loading");
    try {
      const response = await fetch("/api/auth/kwai-link", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kwai_url }),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.error || (portuguese ? "Não foi possível abrir seu perfil. Confira o link." : "无法打开该主页，请检查链接。"));
      creatorUser = result.account;
      localStorage.setItem(authKey, JSON.stringify(creatorUser));
      await loadAccountState();
      resetRepeatableTestFlow();
      updateCreatorName();
      closeAuth(true);
      track("page_view", { source: "after_kwai_link" });
      show(!hasProfile() ? "choose" : "dashboard");
    } catch (error) {
      setAuthStatus(error.message || (portuguese ? "Tente novamente." : "请重试。"), "error");
    } finally {
      setButtonBusy(button, false);
    }
  }, true);

  setAuthMode("login");
  document.querySelector(".landing .cta [data-auth-open='register']")?.remove();
  const ending = document.querySelector(".landing .ending-card small");
  if (ending) ending.textContent = "Cole o link do seu perfil Kwai, escolha suas preferências e encontre roteiros para gravar.";
})();
