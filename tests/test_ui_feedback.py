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

    def test_preference_completion_is_account_scoped(self) -> None:
        self.assertIn('preferences_completed:preferencesCompleted', self.markup)
        self.assertIn('preferencesCompleted=state.preferences_completed===true', self.markup)
        self.assertIn('function hasProfile(){return preferencesCompleted}', self.markup)
        self.assertIn('if(delta>0)finishProfile()', self.markup)

    def test_new_account_can_open_preferences_before_kwai_profile(self) -> None:
        self.assertIn('if(isRepeatableTestAccount()||!hasProfile()||!accountNeedsProfile(creatorUser))', self.markup)
        self.assertIn('v=creatorUser?"choose":"home"', self.markup)

    def test_onboarding_is_versioned_per_account(self) -> None:
        self.assertIn('const CREATOR_ONBOARDING_VERSION=2', self.markup)
        self.assertIn(
            'Number(workspace.creatorOnboardingVersion||0)<CREATOR_ONBOARDING_VERSION',
            self.markup,
        )
        self.assertIn(
            'workspace.creatorOnboardingVersion=CREATOR_ONBOARDING_VERSION',
            self.markup,
        )

    def test_full_script_failure_is_visible_and_retryable(self) -> None:
        self.assertIn('if(!r.ok||!d.complete||!html.trim())', self.markup)
        self.assertIn('data-retry-script=', self.markup)
        self.assertIn('data-script-slot=', self.markup)
        self.assertIn('Não mostramos uma versão resumida.', self.markup)

    def test_script_details_are_not_artificially_truncated(self) -> None:
        self.assertNotIn('return out.slice(0,6)', self.markup)
        self.assertNotIn('d.segments.slice(0,9)', self.markup)

    def test_profile_layout_wraps_mobile_content(self) -> None:
        self.assertIn('class="profile-identity"', self.markup)
        self.assertIn('class="submission-copy"', self.markup)
        self.assertIn('.profile-prefs{display:flex!important;flex-wrap:wrap!important', self.markup)
        self.assertIn('grid-template-columns:88px minmax(0,1fr)!important', self.markup)
        self.assertIn('overflow-wrap:anywhere!important', self.markup)

    def test_profile_gate_has_a_working_back_action(self) -> None:
        self.assertIn('data-auth-back', self.markup)

    def test_888_test_account_restarts_the_full_onboarding_flow(self) -> None:
        self.assertIn('function isRepeatableTestAccount', self.markup)
        self.assertIn('function resetRepeatableTestFlow', self.markup)
        self.assertIn('isRepeatableTestAccount()?"choose"', self.markup)
        self.assertIn('workspace.rewardGuideHidden&&!isRepeatableTestAccount()', self.markup)
        self.assertIn('forceLocalOnboarding||isRepeatableTestAccount()', self.markup)
        self.assertIn('!forceLocalOnboarding&&!isRepeatableTestAccount()', self.markup)
        self.assertIn('function returnFromProfileGate(button)', self.markup)
        self.assertIn('back.classList.toggle("active",authMode==="profile")', self.markup)


if __name__ == "__main__":
    unittest.main()
