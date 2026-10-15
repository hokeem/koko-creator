(() => {
  const form = document.querySelector("#auth-form");
  if (!form) return;

  const registerPassword = document.createElement("input");
  registerPassword.id = "auth-register-password";
  registerPassword.name = "register_password";
  registerPassword.type = "password";
  registerPassword.autocomplete = "new-password";
  registerPassword.minLength = 8;
  registerPassword.maxLength = 128;
  registerPassword.hidden = true;
  document.querySelector("#auth-kwai").before(registerPassword);

  const originalSetAuthMode = setAuthMode;
  setAuthMode = function (mode) {
    originalSetAuthMode(mode);
    const registering = authMode === "register";
    const phone = document.querySelector("#auth-phone");
    const kwai = document.querySelector("#auth-kwai");
    const reason = document.querySelector("#auth-reason");
    const name = document.querySelector("#auth-display-name");
    phone.placeholder = registering ? "Número de celular com DDD" : "Telefone ou ID do Kwai";
    phone.inputMode = registering ? "tel" : "text";
    kwai.placeholder = registering ? "https://www.kwai.com/@seu_id" : "@seu_id_no_kwai";
    kwai.type = registering ? "url" : "text";
    kwai.required = registering;
    registerPassword.hidden = !registering;
    registerPassword.required = registering;
    registerPassword.placeholder = "Crie uma senha (mínimo 8 caracteres)";
    reason.hidden = true;
    reason.disabled = registering;
    if (registering) name.hidden = true;
    document.querySelector("#auth-title").textContent = registering ? "Crie sua conta" : document.querySelector("#auth-title").textContent;
    document.querySelector("#auth-submit").textContent = registering ? "Criar conta e começar" : document.querySelector("#auth-submit").textContent;
    document.querySelector("#auth-guide-copy").textContent = registering
      ? "Cadastre seu telefone, crie uma senha e cole o link do seu perfil Kwai. Seu acesso fica pronto na hora."
      : document.querySelector("#auth-guide-copy").textContent;
    document.querySelector("#auth-switch-copy").textContent = registering ? "Já tem conta?" : "Novo por aqui?";
    document.querySelector("#auth-toggle").textContent = registering ? "Entrar" : "Criar conta";
    const loginPassword = document.querySelector("#auth-password");
    if (loginPassword && !registering) {
      loginPassword.inputMode = "text";
      loginPassword.placeholder = "Sua senha";
    }
    const hint = document.querySelector("#auth-login-hint");
    if (hint && !registering && authMode === "login") {
      hint.textContent = "Use sua senha. Contas antigas continuam com os 4 últimos dígitos do telefone.";
    }
  };

  document.querySelectorAll('[data-auth-open="register"]').forEach(button => {
    button.textContent = "Criar conta grátis";
  });

  form.addEventListener("submit", async event => {
    if (authMode !== "register") return;
    event.preventDefault();
    event.stopImmediatePropagation();
    const button = document.querySelector("#auth-submit");
    if (button.disabled) return;
    const phone = document.querySelector("#auth-phone").value.trim();
    const password = registerPassword.value;
    const kwai_url = document.querySelector("#auth-kwai").value.trim();
    if (!/^\d{10,15}$/.test(phone.replace(/\D/g, ""))) {
      setAuthStatus("Informe um telefone válido com DDD.", "error");
      return;
    }
    if (password.length < 8 || password.length > 128) {
      setAuthStatus("Crie uma senha de 8 a 128 caracteres.", "error");
      return;
    }
    setButtonBusy(button, true, "Criando sua conta...");
    setAuthStatus("Criando sua conta...", "loading");
    try {
      const response = await fetch("/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone, password, kwai_url }),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.error || "Não foi possível criar a conta.");
      creatorUser = result.account;
      localStorage.setItem(authKey, JSON.stringify(creatorUser));
      await loadAccountState();
      updateCreatorName();
      closeAuth(true);
      uiMessage("Conta criada! Escolha suas preferências para começar.", "success", 4000);
      track("page_view", { source: "after_signup" });
      show("choose");
    } catch (error) {
      setAuthStatus(error.message || "Não foi possível criar a conta.", "error");
    } finally {
      setButtonBusy(button, false);
    }
  }, true);
})();
