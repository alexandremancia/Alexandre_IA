"""Auto-cut: filler isolado, falso começo, silêncio, padding e merge."""
import pytest
from conftest import load

autocut = load("autocut")


def word(text, start, end):
    return {"text": text, "start": start, "end": end, "type": "word", "speaker_id": "S0"}


class TestFiller:
    def test_filler_cercado_de_pausa_conta(self):
        words = [word("então", 1.0, 1.3)]
        assert autocut.is_isolated_filler(words, 0, gap_before=0.3, gap_after=0.3)

    def test_filler_dentro_da_frase_nao_conta(self):
        # "tipo de arquivo" — aqui 'tipo' é conteúdo, não vício
        words = [word("tipo", 1.0, 1.2)]
        assert not autocut.is_isolated_filler(words, 0, gap_before=0.05, gap_after=0.05)

    def test_palavra_comum_nunca_conta(self):
        words = [word("arquitetura", 1.0, 1.6)]
        assert not autocut.is_isolated_filler(words, 0, gap_before=1.0, gap_after=1.0)

    def test_normalizacao_ignora_pontuacao_e_caixa(self):
        assert autocut.norm("Né,") == "né"
        assert autocut.norm("UH!") == "uh"


class TestFalsoComeco:
    def test_repeticao_imediata_marca_a_primeira(self):
        toks = ["a", "gente", "vai", "a", "gente", "vai", "fazer"]
        words = [word(t, i * 0.3, i * 0.3 + 0.25) for i, t in enumerate(toks)]
        drop = autocut.detect_false_starts(words)
        assert drop == {0, 1, 2}

    def test_sem_repeticao_nao_marca_nada(self):
        toks = ["hoje", "vamos", "falar", "sobre", "video"]
        words = [word(t, i * 0.3, i * 0.3 + 0.25) for i, t in enumerate(toks)]
        assert autocut.detect_false_starts(words) == set()

    def test_repeticao_de_uma_palavra_nao_conta(self):
        # "muito muito bom" é ênfase, não falso começo
        words = [word(t, i * 0.3, i * 0.3 + 0.25)
                 for i, t in enumerate(["muito", "muito", "bom"])]
        assert autocut.detect_false_starts(words) == set()


class TestFaixas:
    def test_silencio_longo_quebra_o_segmento(self):
        words = [word("um", 0.0, 0.4), word("dois", 3.0, 3.4)]
        ranges, stats = autocut.build_keep_ranges(
            words, max_silence=0.45, pad_in=0.05, pad_out=0.08,
            drop_fillers=False, drop_false_starts=False, drop_breaths=False)
        assert len(ranges) == 2
        assert stats["silence_s"] > 2.0

    def test_silencio_curto_nao_quebra(self):
        words = [word("um", 0.0, 0.4), word("dois", 0.6, 1.0)]
        ranges, _ = autocut.build_keep_ranges(
            words, max_silence=0.45, pad_in=0.05, pad_out=0.08,
            drop_fillers=False, drop_false_starts=False, drop_breaths=False)
        assert len(ranges) == 1

    def test_padding_aplicado_nas_bordas(self):
        words = [word("solo", 1.0, 1.5)]
        ranges, _ = autocut.build_keep_ranges(
            words, max_silence=0.45, pad_in=0.05, pad_out=0.08,
            drop_fillers=False, drop_false_starts=False, drop_breaths=False)
        start, end, _ = ranges[0]
        assert start == pytest.approx(0.95)
        assert end == pytest.approx(1.58)

    def test_padding_nunca_fica_negativo(self):
        words = [word("inicio", 0.01, 0.4)]
        ranges, _ = autocut.build_keep_ranges(
            words, max_silence=0.45, pad_in=0.2, pad_out=0.08,
            drop_fillers=False, drop_false_starts=False, drop_breaths=False)
        assert ranges[0][0] >= 0.0

    def test_padding_nao_faz_faixas_se_sobreporem(self):
        words = [word("um", 0.0, 0.4), word("dois", 3.0, 3.4), word("tres", 3.5, 3.9)]
        ranges, _ = autocut.build_keep_ranges(
            words, max_silence=0.45, pad_in=0.5, pad_out=0.5,
            drop_fillers=False, drop_false_starts=False, drop_breaths=False)
        for i in range(1, len(ranges)):
            assert ranges[i][0] >= ranges[i - 1][1]

    def test_respiracao_removida_evento_expressivo_mantido(self):
        words = [
            word("frase", 0.0, 0.5),
            {"text": "(breathes)", "start": 0.6, "end": 0.9, "type": "audio_event"},
            {"text": "(laughs)", "start": 1.0, "end": 1.4, "type": "audio_event"},
            word("fim", 1.5, 1.9),
        ]
        _, stats = autocut.build_keep_ranges(
            words, max_silence=2.0, pad_in=0.0, pad_out=0.0,
            drop_fillers=False, drop_false_starts=False, drop_breaths=True)
        assert stats["breaths"] == 1


class TestMerge:
    def test_junta_faixas_quase_coladas(self):
        ranges = [(0.0, 1.0, ["a"]), (1.05, 2.0, ["b"])]
        out = autocut.merge_adjacent(ranges, min_gap=0.12)
        assert len(out) == 1
        assert out[0][2] == ["a", "b"]

    def test_mantem_faixas_realmente_separadas(self):
        ranges = [(0.0, 1.0, ["a"]), (2.0, 3.0, ["b"])]
        assert len(autocut.merge_adjacent(ranges, min_gap=0.12)) == 2

    def test_lista_vazia(self):
        assert autocut.merge_adjacent([], 0.12) == []
