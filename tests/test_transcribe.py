"""Transcrição: escolha de motor e conversão do Whisper para o formato Scribe.

O caminho local converte a saída do faster-whisper para o MESMO esquema do
Scribe. Se a conversão divergir, todo o resto (autocut, captions, render) lê
lixo sem nunca acusar erro — os helpers só olham `type`, `start`, `end`,
`text` e `speaker_id`.
"""
import sys
import types
from pathlib import Path

import pytest
from conftest import load

transcribe = load("transcribe")


class FakeWord:
    def __init__(self, word, start, end, probability=0.9):
        self.word = word
        self.start = start
        self.end = end
        self.probability = probability


class FakeSegment:
    def __init__(self, words):
        self.words = words


class FakeInfo:
    language = "pt"
    language_probability = 0.98


def install_fake_whisper(monkeypatch, segments, *, falha=None):
    """Injeta um faster_whisper falso, para testar a conversão sem baixar modelo."""
    mod = types.ModuleType("faster_whisper")

    class FakeModel:
        def __init__(self, *a, **kw):
            if falha:
                raise falha

        def transcribe(self, *a, **kw):
            return iter(segments), FakeInfo()

    mod.WhisperModel = FakeModel
    monkeypatch.setitem(sys.modules, "faster_whisper", mod)


class TestConversaoLocal:
    def _segments(self):
        return [
            FakeSegment([FakeWord(" Hoje", 0.0, 0.4), FakeWord(" eu", 0.45, 0.6)]),
            FakeSegment([FakeWord(" vou", 1.2, 1.5)]),
        ]

    def test_esquema_bate_com_o_scribe(self, monkeypatch, tmp_path):
        install_fake_whisper(monkeypatch, self._segments())
        out = transcribe.transcribe_local(tmp_path / "a.wav")

        assert set(["text", "words"]).issubset(out)
        for w in out["words"]:
            assert set(["text", "start", "end", "type", "speaker_id"]).issubset(w)
            assert w["type"] == "word"

    def test_espacos_do_whisper_sao_removidos(self, monkeypatch, tmp_path):
        # o faster-whisper devolve ' Hoje' com espaço à esquerda
        install_fake_whisper(monkeypatch, self._segments())
        out = transcribe.transcribe_local(tmp_path / "a.wav")
        assert [w["text"] for w in out["words"]] == ["Hoje", "eu", "vou"]

    def test_tempos_preservados_na_ordem(self, monkeypatch, tmp_path):
        install_fake_whisper(monkeypatch, self._segments())
        words = transcribe.transcribe_local(tmp_path / "a.wav")["words"]
        assert [w["start"] for w in words] == [0.0, 0.45, 1.2]
        assert all(w["end"] > w["start"] for w in words)

    def test_palavras_vazias_sao_descartadas(self, monkeypatch, tmp_path):
        install_fake_whisper(monkeypatch, [FakeSegment([
            FakeWord("  ", 0.0, 0.1), FakeWord(" ok", 0.2, 0.5)])])
        words = transcribe.transcribe_local(tmp_path / "a.wav")["words"]
        assert len(words) == 1 and words[0]["text"] == "ok"

    def test_segmento_sem_palavras_nao_quebra(self, monkeypatch, tmp_path):
        install_fake_whisper(monkeypatch, [FakeSegment(None), FakeSegment([])])
        assert transcribe.transcribe_local(tmp_path / "a.wav")["words"] == []

    def test_falante_unico_no_caminho_local(self, monkeypatch, tmp_path):
        # Whisper local não diariza: tudo vira S0, e isso precisa estar explícito
        install_fake_whisper(monkeypatch, self._segments())
        out = transcribe.transcribe_local(tmp_path / "a.wav")
        assert {w["speaker_id"] for w in out["words"]} == {"S0"}

    def test_degradacao_e_declarada_no_payload(self, monkeypatch, tmp_path):
        """Regra Dura 18: o transcript diz o que se perdeu, não só o que tem."""
        install_fake_whisper(monkeypatch, self._segments())
        out = transcribe.transcribe_local(tmp_path / "a.wav")
        assert "faster-whisper" in out["_engine"]
        perdas = " ".join(out["_degraded"]).lower()
        assert "diariza" in perdas and "filler" in perdas

    def test_texto_completo_e_a_juncao_das_palavras(self, monkeypatch, tmp_path):
        install_fake_whisper(monkeypatch, self._segments())
        out = transcribe.transcribe_local(tmp_path / "a.wav")
        assert out["text"] == "Hoje eu vou"

    def test_erro_de_download_explica_as_saidas(self, monkeypatch, tmp_path):
        """O traceback cru de proxy não diz nada sobre o que fazer."""
        install_fake_whisper(monkeypatch, [], falha=OSError("CONNECT tunnel failed: 403"))
        with pytest.raises(RuntimeError) as exc:
            transcribe.transcribe_local(tmp_path / "a.wav")
        msg = str(exc.value)
        assert "huggingface" in msg.lower()
        assert "HF_HOME" in msg
        assert "ELEVENLABS_API_KEY" in msg

    def test_sem_faster_whisper_diz_como_instalar(self, monkeypatch, tmp_path):
        monkeypatch.setitem(sys.modules, "faster_whisper", None)
        with pytest.raises(RuntimeError) as exc:
            transcribe.transcribe_local(tmp_path / "a.wav")
        assert "pip install faster-whisper" in str(exc.value)


class TestChaveOpcional:
    def test_ambiente_e_lido(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("ELEVENLABS_API_KEY", "sk-teste")
        assert transcribe.load_api_key_optional() == "sk-teste"

    def test_sem_chave_devolve_none_em_vez_de_abortar(self, monkeypatch, tmp_path):
        """O load_api_key() original chama sys.exit; o caminho degradável não pode."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
        monkeypatch.setattr(transcribe, "__file__", str(tmp_path / "helpers" / "t.py"))
        assert transcribe.load_api_key_optional() is None

    def test_chave_vazia_conta_como_ausente(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("ELEVENLABS_API_KEY", "")
        monkeypatch.setattr(transcribe, "__file__", str(tmp_path / "helpers" / "t.py"))
        assert transcribe.load_api_key_optional() is None

    def test_env_local_e_lido_e_desempacotado(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
        (tmp_path / ".env").write_text('ELEVENLABS_API_KEY="sk-do-env"\n')
        assert transcribe.load_api_key_optional() == "sk-do-env"
