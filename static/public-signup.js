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
    input.placeholder = portuguese ? "Cole o link ou a mensagem compartilhada do Kwai" : "粘贴 Kwai 主页分享链接或整段分享文字";
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
    document.querySelector("#auth-title").textContent = portuguese ? "Entre com seu perfil do Kwai" : "使用 Kwai 主页进入";
    document.querySelector("#auth-submit").textContent = portuguese ? "Continuar com meu perfil" : "使用主页链接进入";
    const hint = document.querySelector("#auth-login-hint");
    hint.hidden = false;
    hint.innerHTML = portuguese
      ? "Cole o link público do <strong>seu perfil</strong> no Kwai. A Koko usa esse endereço para reunir seus roteiros e vídeos enviados. Não pedimos sua senha do Kwai."
      : "粘贴你的 Kwai 作者主页公开链接。Koko 会用它归集脚本与回传视频，不会要求你的 Kwai 密码。";
    let note = document.querySelector("#auth-link-note");
    if (!note) {
      note = document.createElement("p");
      note.id = "auth-link-note";
      note.className = "auth-link-note";
      input.after(note);
    }
    note.textContent = portuguese
      ? "Pode colar a mensagem inteira de compartilhamento do perfil. Links de vídeos não são aceitos. O link não confirma a titularidade do perfil."
      : "可以粘贴整段主页分享文字；视频链接不能用于进入。公开链接无法验证主页归属。";
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
