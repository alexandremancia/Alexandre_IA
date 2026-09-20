"""QC: fronteiras da timeline, parsing de legenda e colisão com overlay."""
import pytest
from conftest import load

qc = load("qc")


class TestFronteiras:
    def test_junções_e_duracao_total(self):
        edl = {"ranges": [{"start": 0, "end": 2}, {"start": 5, "end": 8}, {"start": 0, "end": 1}]}
        bounds, total = qc.edl_boundaries(edl)
        assert total == pytest.approx(6.0)
        assert bounds == [2.0, 5.0]      # o fim do arquivo não é junção

    def test_segmento_unico_nao_tem_juncao(self):
        bounds, total = qc.edl_boundaries({"ranges": [{"start": 0, "end": 4}]})
        assert bounds == []
        assert total == pytest.approx(4.0)

    def test_speed_encurta_a_duracao_esperada(self):
        edl = {"ranges": [{"start": 0, "end": 4, "speed": 2.0}]}
        _, total = qc.edl_boundaries(edl)
        assert total == pytest.approx(2.0)

    def test_edl_vazio(self):
        assert qc.edl_boundaries({"ranges": []}) == ([], 0.0)


class TestParsingDeTempo:
    def test_ass(self):
        assert qc.ass_secs("0:00:01.50") == pytest.approx(1.5)
        assert qc.ass_secs("1:01:01.23") == pytest.approx(3661.23)

    def test_srt(self):
        assert qc.srt_secs("00:00:01,500") == pytest.approx(1.5)
        assert qc.srt_secs("01:01:01,230") == pytest.approx(3661.23)


class TestSobreposicao:
    def test_janelas_que_se_cruzam(self):
        assert qc.overlaps((0, 2), (1, 3))

    def test_janelas_disjuntas(self):
        assert not qc.overlaps((0, 1), (2, 3))

    def test_encostadas_nao_sobrepoem(self):
        assert not qc.overlaps((0, 1), (1, 2))


class TestLegenda:
    def _ass(self, tmp_path, margin=90):
        p = tmp_path / "s.ass"
        p.write_text(
            "[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
            "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
            "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            f"Style: Default,Helvetica,18,&H00FFFFFF,&H00FF5A00,&H00000000,&H00000000,1,0,0,0,"
            f"100,100,0,0,1,2,0,2,60,60,{margin},1\n\n"
            "[Events]\n"
            "Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,OLA MUNDO\n"
            "Dialogue: 0,0:00:04.00,0:00:06.00,Default,,0,0,0,,SEGUNDA LINHA\n"
        )
        return p

    def test_le_margem_do_estilo(self, tmp_path):
        assert qc.parse_ass_margin(self._ass(tmp_path, margin=90)) == 90

    def test_le_janelas_de_tempo(self, tmp_path):
        assert qc.subtitle_times(self._ass(tmp_path)) == [(1.0, 3.0), (4.0, 6.0)]

    def test_srt_tambem(self, tmp_path):
        p = tmp_path / "s.srt"
        p.write_text("1\n00:00:01,000 --> 00:00:03,000\nOLA\n\n")
        assert qc.subtitle_times(p) == [(1.0, 3.0)]

    def test_overlay_sem_geometria_vira_aviso(self, tmp_path):
        sub = self._ass(tmp_path)
        edl = {"subtitles": str(sub),
               "overlays": [{"start_in_output": 1.5, "duration": 1.0}]}
        checks = qc.check_caption_collision(edl, tmp_path, 10.0)
        assert any(c.level == "warn" for c in checks)

    def test_overlay_com_geometria_declarada_passa(self, tmp_path):
        sub = self._ass(tmp_path)
        edl = {"subtitles": str(sub),
               "overlays": [{"start_in_output": 1.5, "duration": 1.0, "x": 0, "y": 100}]}
        checks = qc.check_caption_collision(edl, tmp_path, 10.0)
        assert all(c.level == "ok" for c in checks)

    def test_overlay_fora_da_janela_da_legenda_passa(self, tmp_path):
        sub = self._ass(tmp_path)
        edl = {"subtitles": str(sub),
               "overlays": [{"start_in_output": 7.0, "duration": 1.0}]}
        checks = qc.check_caption_collision(edl, tmp_path, 10.0)
        assert all(c.level == "ok" for c in checks)

    def test_margem_baixa_demais_avisa(self, tmp_path):
        sub = self._ass(tmp_path, margin=20)
        edl = {"subtitles": str(sub), "overlays": [{"start_in_output": 1.5, "duration": 1.0, "y": 50}]}
        checks = qc.check_caption_collision(edl, tmp_path, 10.0)
        assert any("safe-zone" in c.name for c in checks if c.level == "warn")

    def test_legenda_ausente_no_disco_e_falha(self, tmp_path):
        edl = {"subtitles": str(tmp_path / "nao_existe.ass"), "overlays": []}
        checks = qc.check_caption_collision(edl, tmp_path, 10.0)
        assert any(c.level == "fail" for c in checks)
