"""Beats: detecção em numpy, snap de EDL e detecção de viradas."""
import numpy as np
import pytest
from conftest import load

beats = load("beats")


def click_track(bpm=120.0, seconds=8.0, sr=22050):
    """Pista sintética: um clique a cada batida. Verdade conhecida para o teste."""
    n = int(sr * seconds)
    y = np.zeros(n, dtype=np.float32)
    period = 60.0 / bpm
    t = 0.0
    while t < seconds:
        i = int(t * sr)
        # clique curto com decaimento — tem transiente, que é o que o onset detecta
        dur = int(sr * 0.02)
        env = np.exp(-np.linspace(0, 6, min(dur, n - i)))
        y[i:i + len(env)] += env * np.sin(2 * np.pi * 1200 * np.arange(len(env)) / sr)
        t += period
    return y, sr


class TestDeteccao:
    def test_tempo_bate_com_a_pista(self):
        y, sr = click_track(bpm=120.0)
        env, hop = beats.onset_envelope(y, sr)
        bpm = beats.estimate_tempo(env, sr, hop)
        # aceita a oitava metade/dobro, que é ambiguidade real de detecção de tempo
        assert any(abs(bpm - alvo) < 6 for alvo in (60, 120, 240)), bpm

    def test_envelope_tem_picos_nas_batidas(self):
        y, sr = click_track(bpm=120.0, seconds=4.0)
        env, hop = beats.onset_envelope(y, sr)
        assert env.max() == pytest.approx(1.0)     # normalizado
        assert env.mean() < 0.3                    # esparso, não platô

    def test_silencio_nao_inventa_tempo(self):
        y = np.zeros(22050 * 3, dtype=np.float32)
        env, hop = beats.onset_envelope(y, 22050)
        assert env.max() == 0.0

    def test_audio_curto_demais_nao_quebra(self):
        env, hop = beats.onset_envelope(np.zeros(100, dtype=np.float32), 22050)
        assert len(env) >= 1
        assert beats.estimate_tempo(env, 22050, hop) == 0.0

    def test_grade_de_batidas_e_regular(self):
        y, sr = click_track(bpm=120.0, seconds=8.0)
        env, hop = beats.onset_envelope(y, sr)
        grade = beats.beats_from_tempo(env, sr, hop, 120.0)
        assert len(grade) > 10
        deltas = np.diff(grade)
        assert np.std(deltas) < 0.02               # espaçamento uniforme

    def test_bpm_zero_devolve_grade_vazia(self):
        assert beats.beats_from_tempo(np.zeros(10), 22050, 512, 0.0) == []


class TestSnap:
    def _edl(self):
        return {"ranges": [{"source": "A", "start": 10.0, "end": 12.1},
                           {"source": "A", "start": 20.0, "end": 22.0}]}

    def test_borda_perto_da_batida_e_puxada(self):
        # segmento 0 termina em 2.1s na saída; batida em 2.0 está a 0.1 de distância
        edl, moved = beats.snap_edl(self._edl(), [0.0, 2.0, 4.0], tolerance=0.25)
        assert moved >= 1

    def test_borda_longe_nao_e_movida(self):
        edl, moved = beats.snap_edl(self._edl(), [0.0, 50.0], tolerance=0.25)
        assert moved == 0

    def test_tolerancia_e_respeitada(self):
        """Nunca mover além da tolerância — cortar fora da palavra quebra a Regra Dura 6."""
        original = self._edl()
        antes = [(s["start"], s["end"]) for s in original["ranges"]]
        edl, _ = beats.snap_edl(original, [0.0, 2.0, 4.0], tolerance=0.25)
        for (s0, e0), seg in zip(antes, edl["ranges"]):
            assert abs(seg["start"] - s0) <= 0.25
            assert abs(seg["end"] - e0) <= 0.25

    def test_sem_batidas_nao_move_nada(self):
        edl, moved = beats.snap_edl(self._edl(), [], tolerance=0.25)
        assert moved == 0


class TestViradas:
    def test_acha_o_salto_de_energia(self):
        energia = [[i * 0.1, 0.1] for i in range(60)] + [[6.0 + i * 0.1, 0.9] for i in range(60)]
        secoes = beats.find_sections(energia, n=3)
        assert secoes
        assert any(5.0 < t < 7.5 for t in secoes)

    def test_energia_constante_nao_inventa_virada(self):
        energia = [[i * 0.1, 0.5] for i in range(120)]
        assert beats.find_sections(energia, n=5) == []

    def test_entrada_curta_devolve_vazio(self):
        assert beats.find_sections([[0.0, 0.1], [0.1, 0.2]]) == []

    def test_viradas_nao_se_amontoam(self):
        energia = [[i * 0.1, 0.1 if (i // 20) % 2 == 0 else 0.9] for i in range(200)]
        secoes = beats.find_sections(energia, n=6)
        for a, b in zip(secoes, secoes[1:]):
            assert b - a > 4.0
