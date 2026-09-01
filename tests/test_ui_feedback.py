import unittest

import app


class CreatorUiFeedbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.markup = app.page_html()

    def test_login_has_visible_progress_and_inline_result(self) -> None:
        self.assertIn('id="auth-status" role="status" aria-live="polite"', self.markup)
        self.assertIn('loginLoading:zh?"正在登录...":"Entrando..."', self.markup)
        self.assertIn('setButtonBusy(button,true,loading)', self.markup)
        self.assertIn('setAuthStatus(message,"error")', self.markup)

    def test_global_controls_have_immediate_feedback(self) -> None:
        self.assertIn('id="ui-toast" role="status" aria-live="polite"', self.markup)
        self.assertIn('document.addEventListener("pointerdown"', self.markup)
        self.assertIn('pulseControl(control)', self.markup)

    def test_async_creator_actions_report_progress(self) -> None:
        self.assertIn('Carregando mais roteiros...', self.markup)
        self.assertIn('Enviando vídeo para revisão...', self.markup)
        self.assertIn('Processando imagem...', self.markup)
        self.assertIn('Saindo da conta...', self.markup)
        self.assertIn('Carregando sua biblioteca...', self.markup)
        self.assertIn('Nao foi possivel sincronizar suas alteracoes.', self.markup)


if __name__ == "__main__":
    unittest.main()
