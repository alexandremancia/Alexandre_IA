"""Reframe: os três freios que impedem tremor (Regra Dura 15)."""
import pytest
from conftest import load

reframe = load("reframe")


class TestSuavizacao:
    def _times(self, n, dt=0.25):
        return [i * dt for i in range(n)]

    def test_zona_morta_ignora_micro_movimento(self):
        vals = [500, 505, 498, 502, 501, 499]     # ruído de ±5px
        out = reframe.smooth_track(vals, self._times(6), window_s=0.5,
                                   deadzone=24.0, max_speed=1000)
        assert max(out) - min(out) < 5            # câmera praticamente parada

    def test_movimento_real_e_seguido(self):
        vals = [500] * 4 + [900] * 8
        out = reframe.smooth_track(vals, self._times(12), window_s=0.5,
                                   deadzone=24.0, max_speed=1000)
        assert out[-1] > 800                      # chegou perto do destino

    def test_limite_de_velocidade_impede_salto(self):
        vals = [0, 2000]
        out = reframe.smooth_track(vals, [0.0, 0.25], window_s=0.1,
                                   deadzone=1.0, max_speed=100)
        # 100 px/s * 0.25s = 25px por passo, no máximo
        assert out[1] - out[0] <= 26

    def test_saida_tem_o_mesmo_tamanho_da_entrada(self):
        vals = [100, 200, 300, 400]
        out = reframe.smooth_track(vals, self._times(4), 0.5, 10.0, 500)
        assert len(out) == len(vals)

    def test_lista_vazia_nao_quebra(self):
        assert reframe.smooth_track([], [], 1.0, 10.0, 100) == []

    def test_suavizado_treme_menos_que_o_cru(self):
        cru = [500, 560, 490, 570, 480, 565, 495]
        times = self._times(7)
        suave = reframe.smooth_track(cru, times, window_s=1.0, deadzone=24.0, max_speed=200)
        dt = 0.25
        assert reframe.jitter_score([int(v) for v in suave], dt) < \
               reframe.jitter_score(cru, dt)


class TestTremor:
    """Inversão de direção, não velocidade, é o que distingue tremor de panorâmica."""

    def test_panoramica_suave_nao_conta_como_tremor(self):
        # sujeito atravessando o quadro: rápido, mas sempre na mesma direção
        pan = [i * 30 for i in range(12)]
        assert reframe.jitter_score(pan, 0.25) == pytest.approx(120.0)  # rápido
        assert reframe.reversal_rate(pan, 0.25) == 0.0                  # sem tremor

    def test_vai_e_volta_conta_como_tremor(self):
        shake = [500, 530, 500, 530, 500, 530, 500]
        assert reframe.reversal_rate(shake, 0.25) > 1.0

    def test_camera_parada_nao_tem_inversao(self):
        assert reframe.reversal_rate([500] * 10, 0.25) == 0.0

    def test_ruido_de_arredondamento_nao_conta_como_direcao(self):
        # oscilação de 1px é arredondamento do crop, não movimento de câmera
        ruido = [500, 501, 500, 501, 500, 501]
        assert reframe.reversal_rate(ruido, 0.25, min_step=2.0) == 0.0

    def test_poucas_amostras(self):
        assert reframe.reversal_rate([100, 200], 0.25) == 0.0


class TestDetectorDeRosto:
    def test_fabrica_devolve_par(self):
        detect, info = reframe.make_face_detector()
        assert (detect is None) or callable(detect)
        assert isinstance(info, str) and info

    def test_modelo_ausente_explica_como_obter(self, tmp_path):
        """Regra Dura 19: degradar é permitido, degradar calado não é."""
        import cv2
        if not hasattr(cv2, "FaceDetectorYN") or hasattr(cv2, "CascadeClassifier"):
            pytest.skip("caminho YuNet só existe no OpenCV 5.x")
        detect, motivo = reframe.make_face_detector(tmp_path / "nao_existe.onnx")
        assert detect is None
        assert "curl" in motivo and "movimento" in motivo

    def test_url_do_modelo_aponta_para_o_lfs(self):
        # /raw/ devolveria o ponteiro de texto do LFS, que falha só no parse do ONNX
        assert "media.githubusercontent.com/media/" in reframe.YUNET_URL
        assert reframe.YUNET_URL.endswith(".onnx")


class TestCrop:
    def test_centro_vira_canto_superior_esquerdo(self):
        assert reframe.clamp_crop([960.0], crop_size=608, frame_size=1920) == [656]

    def test_preso_na_borda_esquerda(self):
        assert reframe.clamp_crop([10.0], crop_size=608, frame_size=1920) == [0]

    def test_preso_na_borda_direita(self):
        assert reframe.clamp_crop([1910.0], crop_size=608, frame_size=1920) == [1312]

    def test_crop_do_tamanho_do_quadro_fica_em_zero(self):
        assert reframe.clamp_crop([500.0], crop_size=1920, frame_size=1920) == [0]


class TestJitter:
    def test_posicao_parada_nao_treme(self):
        assert reframe.jitter_score([100] * 10, 0.25) == 0.0

    def test_valor_em_px_por_segundo(self):
        # 25px por amostra a cada 0.25s = 100 px/s
        pos = [i * 25 for i in range(5)]
        assert reframe.jitter_score(pos, 0.25) == pytest.approx(100.0)

    def test_uma_amostra_so(self):
        assert reframe.jitter_score([100], 0.25) == 0.0


class TestAspectos:
    def test_catalogo_bate_com_os_tamanhos(self):
        assert set(reframe.ASPECTS) == set(reframe.OUT_SIZES)

    def test_proporcao_de_saida_confere(self):
        for name, (aw, ah) in reframe.ASPECTS.items():
            ow, oh = reframe.OUT_SIZES[name]
            assert ow / oh == pytest.approx(aw / ah, rel=0.01), name

    def test_dimensoes_de_saida_sao_pares(self):
        for ow, oh in reframe.OUT_SIZES.values():
            assert ow % 2 == 0 and oh % 2 == 0
