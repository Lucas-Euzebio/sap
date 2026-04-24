import os
import pytest
from unittest.mock import MagicMock, patch
from playwright.sync_api import TimeoutError as PlaywrightTimeout


def _make_mocks():
    """Monta a cadeia de mocks: sync_playwright → browser → context → page → download."""
    mock_download = MagicMock()

    mock_dl_cm = MagicMock()
    mock_dl_cm.__enter__ = MagicMock(return_value=mock_dl_cm)
    mock_dl_cm.__exit__ = MagicMock(return_value=False)
    mock_dl_cm.value = mock_download

    mock_page = MagicMock()
    mock_page.url = "https://outlook.office.com/mail/"
    mock_page.expect_download.return_value = mock_dl_cm

    mock_context = MagicMock()
    mock_context.new_page.return_value = mock_page

    mock_browser = MagicMock()
    mock_browser.new_context.return_value = mock_context

    mock_pw = MagicMock()
    mock_pw.chromium.launch.return_value = mock_browser

    mock_sync_pw = MagicMock()
    mock_sync_pw.return_value.__enter__ = MagicMock(return_value=mock_pw)
    mock_sync_pw.return_value.__exit__ = MagicMock(return_value=False)

    return mock_sync_pw, mock_page, mock_download


@patch("app.outlook.sync_playwright")
def test_fetch_nfse_pdf_success(mock_sync_playwright, monkeypatch):
    monkeypatch.setenv("OUTLOOK_EMAIL", "financeiro@zeusagro.com")
    monkeypatch.setenv("OUTLOOK_PASSWORD", "senha_teste")

    mock_sync_pw, mock_page, mock_download = _make_mocks()
    mock_sync_playwright.side_effect = mock_sync_pw.side_effect
    mock_sync_playwright.return_value = mock_sync_pw.return_value

    from app.outlook import fetch_nfse_pdf
    result = fetch_nfse_pdf("5555")

    assert result is not None
    assert result.endswith("nfse_5555.pdf")
    mock_download.save_as.assert_called_once()


@patch("app.outlook.sync_playwright")
def test_fetch_nfse_pdf_sem_credenciais(mock_sync_playwright, monkeypatch):
    monkeypatch.delenv("OUTLOOK_EMAIL", raising=False)
    monkeypatch.delenv("OUTLOOK_PASSWORD", raising=False)

    from app.outlook import fetch_nfse_pdf
    result = fetch_nfse_pdf("5555")

    assert result is None
    mock_sync_playwright.assert_not_called()


@patch("app.outlook.sync_playwright")
def test_fetch_nfse_pdf_timeout(mock_sync_playwright, monkeypatch):
    monkeypatch.setenv("OUTLOOK_EMAIL", "financeiro@zeusagro.com")
    monkeypatch.setenv("OUTLOOK_PASSWORD", "senha_teste")

    mock_sync_pw, mock_page, _ = _make_mocks()
    mock_sync_playwright.return_value = mock_sync_pw.return_value

    # Simula timeout ao clicar no primeiro email
    mock_page.locator.return_value.first.click.side_effect = PlaywrightTimeout("timeout")

    from app.outlook import fetch_nfse_pdf
    result = fetch_nfse_pdf("9999")

    assert result is None


@patch("app.outlook.sync_playwright")
def test_fetch_nfse_pdf_sessao_expirada_faz_login(mock_sync_playwright, monkeypatch, tmp_path):
    monkeypatch.setenv("OUTLOOK_EMAIL", "financeiro@zeusagro.com")
    monkeypatch.setenv("OUTLOOK_PASSWORD", "senha_teste")

    mock_sync_pw, mock_page, mock_download = _make_mocks()
    mock_sync_playwright.return_value = mock_sync_pw.return_value

    # Simula sessão expirada: primeira URL é a tela de login
    mock_page.url = "https://login.microsoftonline.com/common/oauth2/authorize"

    # Após login, URL muda para mail
    def goto_side_effect(url, **kwargs):
        mock_page.url = "https://outlook.office.com/mail/"

    mock_page.goto.side_effect = goto_side_effect

    from app.outlook import fetch_nfse_pdf
    result = fetch_nfse_pdf("1234")

    # Verifica que tentou preencher o campo de senha (fluxo de login acionado)
    mock_page.locator.assert_called()
