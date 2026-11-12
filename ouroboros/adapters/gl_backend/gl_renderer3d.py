# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""`IRenderer3D` em ModernGL (OpenGL 3.3), ROADMAP M21.

O 3D e desenhado num framebuffer proprio (na resolucao interna do `Estilo3D`, com
z-buffer) e depois composto na tela ampliado sem suavizar, com grao e vinheta. Tudo que o
renderizador de CPU da vitrine (`games/vitrine_estilos/tres_d.py`) fazia por triangulo em
numpy aqui roda num shader: a luz por vertice, o tremor (vertice grudado no pixel), a cor
afim, a neblina pela profundidade e os 15 bits com pontilhado.

Funciona com qualquer contexto ModernGL: o da janela (`GLRenderer`) ou um sem janela
(`moderngl.create_standalone_context()`, usado nos testes e em benchmarks).
"""
from __future__ import annotations

import math
from typing import Dict, Optional, Tuple

import moderngl
import numpy as np

from ouroboros.interfaces.renderer3d import (
    MAX_LUZES,
    Estilo3D,
    Iluminacao3D,
    IRenderer3D,
    Vec3,
)

_VERT = """
#version 330
in vec3 in_pos; in vec3 in_normal; in vec3 in_cor; in float in_emiss;
uniform mat4 u_vp; uniform mat4 u_modelo;
uniform vec3 u_ceu; uniform vec3 u_solo;
uniform int u_nluz;
uniform vec4 u_luz_a[8];    // xyz: direcao (dir) ou posicao; w: 0 dir, 1 ponto, 2 foco
uniform vec4 u_luz_cor[8];  // rgb; w: alcance
uniform vec4 u_luz_dir[8];  // foco: xyz para onde aponta
uniform vec2 u_luz_cone[8]; // foco: cos da borda, cos do miolo
uniform vec2 u_res; uniform int u_tremor;
out vec3 v_cor; noperspective out vec3 v_cor_afim; flat out vec3 v_cor_chapada;
out float v_prof; flat out float v_emiss;
void main() {
    vec4 mundo = u_modelo * vec4(in_pos, 1.0);
    vec4 clip = u_vp * mundo;
    if (u_tremor == 1 && clip.w > 0.0) {  // o vertice gruda no pixel inteiro: o tremor do PS1
        vec2 ndc = clip.xy / clip.w;
        ndc = (floor((ndc * 0.5 + 0.5) * u_res + 0.5) / u_res) * 2.0 - 1.0;
        clip.xy = ndc * clip.w;
    }
    gl_Position = clip;
    v_prof = clip.w;
    vec3 n = normalize(mat3(u_modelo) * in_normal);
    vec3 luz = mix(u_solo, u_ceu, n.y * 0.5 + 0.5);
    for (int i = 0; i < u_nluz; i++) {
        int tipo = int(u_luz_a[i].w + 0.5);
        if (tipo == 0) { luz += max(dot(n, u_luz_a[i].xyz), 0.0) * u_luz_cor[i].rgb; continue; }
        vec3 d = u_luz_a[i].xyz - mundo.xyz;
        float dist = length(d) + 1e-6;
        float k = max(dot(n, d) / dist, 0.0) * pow(clamp(1.0 - dist / u_luz_cor[i].w, 0.0, 1.0), 2.0);
        if (tipo == 2) k *= smoothstep(u_luz_cone[i].x, u_luz_cone[i].y, dot(-d / dist, u_luz_dir[i].xyz));
        luz += k * u_luz_cor[i].rgb;
    }
    vec3 cor = in_cor / 255.0;
    v_emiss = in_emiss;
    v_cor = in_emiss > 0.5 ? cor : cor * luz;
    v_cor_afim = v_cor;
    v_cor_chapada = v_cor;
}
"""

_FRAG = """
#version 330
in vec3 v_cor; noperspective in vec3 v_cor_afim; flat in vec3 v_cor_chapada;
in float v_prof; flat in float v_emiss;
uniform int u_modo;
uniform vec3 u_neb_cor; uniform vec2 u_neb; uniform float u_neb_max;
uniform int u_bits; uniform int u_pontilhado;
out vec4 f_cor;
const float BAYER[16] = float[16](0., 8., 2., 10., 12., 4., 14., 6., 3., 11., 1., 9., 15., 7., 13., 5.);
void main() {
    vec3 c = u_modo == 1 ? v_cor_afim : (u_modo == 2 ? v_cor_chapada : v_cor);
    if (v_emiss < 0.5) {
        float f = clamp((v_prof - u_neb.x) / (u_neb.y - u_neb.x), 0.0, 1.0) * u_neb_max;
        c = mix(c, u_neb_cor, f);
    }
    if (u_bits > 0) {
        float niveis = exp2(float(u_bits)) - 1.0;
        float b = 0.0;
        if (u_pontilhado == 1) {
            ivec2 p = ivec2(gl_FragCoord.xy) % 4;
            b = BAYER[p.y * 4 + p.x] / 16.0 - 0.5;
        }
        c = floor(clamp(c, 0.0, 1.0) * niveis + 0.5 + b) / niveis;
    }
    f_cor = vec4(clamp(c, 0.0, 1.0), 1.0);
}
"""

_QUAD_VERT = """
#version 330
in vec2 in_pos; out vec2 v_uv;
void main() { v_uv = in_pos * 0.5 + 0.5; gl_Position = vec4(in_pos, 0.0, 1.0); }
"""

_QUAD_FRAG = """
#version 330
uniform sampler2D u_tex; uniform vec2 u_res; uniform float u_grao; uniform float u_vinheta;
uniform float u_semente; uniform float u_vhs; uniform float u_tempo; uniform float u_espelhar;
in vec2 v_uv; out vec4 f_cor;
float ruido(vec2 p) { return fract(sin(dot(p, vec2(12.9898, 78.233)) + u_semente) * 43758.5453); }
float ruido1(float y) { return fract(sin(y * 91.3458 + u_semente) * 47453.5453); }
void main() {
    vec2 uv = vec2(mix(v_uv.x, 1.0 - v_uv.x, u_espelhar), v_uv.y);
    float faixa = 0.0;
    if (u_vhs > 0.0) {  // a fita: linhas que tremem, blocos que escorregam e a faixa de tracking subindo
        float linha = floor(uv.y * u_res.y);
        float bloco = step(0.97 - 0.06 * u_vhs, ruido1(floor(uv.y * 18.0) + floor(u_tempo * 6.0)));
        faixa = smoothstep(0.07, 0.0, abs(uv.y - fract(1.0 - u_tempo * 0.11))) * u_vhs;
        uv.x += (ruido1(linha) - 0.5) * 0.004 * u_vhs + (bloco * 0.03 + faixa * 0.05) * u_vhs * (ruido1(linha + 7.0) - 0.5);
    }
    vec4 c = texture(u_tex, uv);
    if (u_vhs > 0.0) {
        float ab = 0.003 * u_vhs;
        c.r = texture(u_tex, uv + vec2(ab, 0.0)).r;
        c.b = texture(u_tex, uv - vec2(ab, 0.0)).b;
        c.rgb = mix(c.rgb, vec3(dot(c.rgb, vec3(0.299, 0.587, 0.114))), 0.35 * u_vhs);
        c.rgb += faixa * 0.35 * ruido(floor(v_uv * u_res) + 3.0);
    }
    c.rgb += (ruido(floor(v_uv * u_res)) - 0.5) * u_grao;
    vec2 d = (v_uv - 0.5) * 2.0;
    c.rgb *= clamp(1.0 + 0.15 * u_vinheta - 0.55 * u_vinheta * dot(d, d), 0.0, 1.0);
    f_cor = c;
}
"""


def perspectiva(fov_y: float, aspecto: float, perto: float, longe: float) -> np.ndarray:
    t = 1.0 / math.tan(fov_y / 2)
    return np.array([[t / aspecto, 0, 0, 0], [0, t, 0, 0],
                     [0, 0, (longe + perto) / (perto - longe), 2 * longe * perto / (perto - longe)],
                     [0, 0, -1, 0]], dtype=np.float64)


def olhar_para(pos, alvo, cima=(0.0, 1.0, 0.0)) -> np.ndarray:
    pos, alvo = np.asarray(pos, dtype=np.float64), np.asarray(alvo, dtype=np.float64)
    f = alvo - pos
    f /= np.linalg.norm(f)
    s = np.cross(f, cima)
    s /= np.linalg.norm(s)
    u = np.cross(s, f)
    return np.array([[*s, -s @ pos], [*u, -u @ pos], [*-f, f @ pos], [0, 0, 0, 1]], dtype=np.float64)


def _mat(m: np.ndarray) -> bytes:
    return np.ascontiguousarray(m.T, dtype="f4").tobytes()  # o GL le por coluna


class ModernGLRenderer3D(IRenderer3D):
    def __init__(self, ctx: "moderngl.Context", largura: int, altura: int) -> None:
        self._ctx = ctx
        self._tela = (largura, altura)
        self._prog = ctx.program(vertex_shader=_VERT, fragment_shader=_FRAG)
        self._quad_prog = ctx.program(vertex_shader=_QUAD_VERT, fragment_shader=_QUAD_FRAG)
        quad = np.array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1], dtype="f4")
        self._quad_vbo = ctx.buffer(quad.tobytes())
        self._quad = ctx.vertex_array(self._quad_prog, [(self._quad_vbo, "2f", "in_pos")])
        self._malhas: Dict[int, Tuple["moderngl.Buffer", "moderngl.VertexArray", int]] = {}
        self._proximo_id = 1
        self._fbo: Optional["moderngl.Framebuffer"] = None
        self._cor: Optional["moderngl.Texture"] = None
        self._res_fbo: Tuple[int, int] = (0, 0)
        self._estilo = Estilo3D()
        self._iluminacao = Iluminacao3D()
        self._vp = np.eye(4)
        self._quadro = 0
        self.desenhou = False  # algo 3D saiu neste quadro (senao a tela fica so com a UI)
        self.definir_camera((0.0, 1.0, 5.0), (0.0, 1.0, 0.0))

    # ------------------------------------------------------------ malhas
    @staticmethod
    def _vertices(posicoes, cores, emissivo) -> bytes:
        p = np.asarray(posicoes, dtype=np.float32).reshape(-1, 3)
        tri = p.reshape(-1, 3, 3)
        n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        n /= np.linalg.norm(n, axis=1)[:, None] + 1e-12
        e = np.zeros(len(p), np.float32) if emissivo is None else np.asarray(emissivo, np.float32)
        dados = np.hstack([p, np.repeat(n, 3, axis=0), np.asarray(cores, np.float32).reshape(-1, 3), e[:, None]])
        return dados.astype("f4").tobytes()

    def criar_malha(self, posicoes, cores, emissivo=None, dinamica: bool = False) -> int:
        dados = self._vertices(posicoes, cores, emissivo)
        vbo = self._ctx.buffer(dados, dynamic=dinamica)
        vao = self._ctx.vertex_array(self._prog, [(vbo, "3f 3f 3f 1f", "in_pos", "in_normal", "in_cor", "in_emiss")])
        mid = self._proximo_id
        self._proximo_id += 1
        self._malhas[mid] = (vbo, vao, len(dados) // 40)
        return mid

    def atualizar_malha(self, malha_id: int, posicoes, cores, emissivo=None) -> None:
        vbo, vao, _ = self._malhas[malha_id]
        dados = self._vertices(posicoes, cores, emissivo)
        if len(dados) > vbo.size:
            vbo.orphan(len(dados))
        vbo.write(dados)
        self._malhas[malha_id] = (vbo, vao, len(dados) // 40)

    def remover_malha(self, malha_id: int) -> None:
        vbo, vao, _ = self._malhas.pop(malha_id)
        vao.release()
        vbo.release()

    # ------------------------------------------------------------ estado do quadro
    def definir_camera(self, posicao: Vec3, alvo: Vec3, fov_vertical_graus: float = 60.0,
                       perto: float = 0.1, longe: float = 200.0) -> None:
        w, h = self._estilo.resolucao or self._tela
        self._camera = (posicao, alvo, fov_vertical_graus, perto, longe)
        self._vp = perspectiva(math.radians(fov_vertical_graus), w / h, perto, longe) @ olhar_para(posicao, alvo)

    def definir_iluminacao(self, iluminacao: Iluminacao3D) -> None:
        self._iluminacao = iluminacao

    def definir_estilo(self, estilo: Estilo3D) -> None:
        self._estilo = estilo
        self.definir_camera(*self._camera)  # o aspecto pode ter mudado

    def _comecar(self) -> None:
        res = self._estilo.resolucao or self._tela
        if res != self._res_fbo:
            if self._fbo is not None:
                self._fbo.release()
                self._cor.release()
            self._cor = self._ctx.texture(res, 3)
            self._cor.filter = (moderngl.NEAREST, moderngl.NEAREST)  # ampliado sem suavizar
            self._fbo = self._ctx.framebuffer([self._cor], self._ctx.depth_renderbuffer(res))
            self._res_fbo = res
        self._fbo.use()
        self._fbo.clear(*self._estilo.fundo, 1.0, depth=1.0)
        self._ctx.enable(moderngl.DEPTH_TEST)
        self._ctx.disable(moderngl.CULL_FACE)  # fitas e planos de um lado so tambem aparecem
        self.desenhou = True

    def _uniformes(self) -> None:
        p, e, il = self._prog, self._estilo, self._iluminacao
        luzes = list(il.luzes)[:MAX_LUZES]
        a = np.zeros((MAX_LUZES, 4), "f4")
        cor = np.zeros((MAX_LUZES, 4), "f4")
        dire = np.zeros((MAX_LUZES, 4), "f4")
        cone = np.zeros((MAX_LUZES, 2), "f4")
        for i, luz in enumerate(luzes):
            tipo = {"dir": 0, "ponto": 1, "foco": 2}[luz.tipo]
            v = np.asarray(luz.vetor, dtype=np.float64)
            a[i] = (*(v / np.linalg.norm(v) if tipo == 0 else v), tipo)
            cor[i] = (*luz.cor, luz.alcance)
            d = np.asarray(luz.direcao, dtype=np.float64)
            dire[i, :3] = d / np.linalg.norm(d)
            cone[i] = luz.cone
        valores = {
            "u_vp": _mat(self._vp), "u_ceu": il.ceu, "u_solo": il.solo, "u_nluz": len(luzes),
            "u_res": tuple(float(x) for x in self._res_fbo), "u_tremor": int(e.tremor), "u_modo": e.modo_cor,
            "u_neb_cor": e.neblina_cor, "u_neb": e.neblina, "u_neb_max": e.neblina_max,
            "u_bits": e.bits_cor, "u_pontilhado": int(e.pontilhado),
        }
        for nome, valor in valores.items():
            if nome in p:
                if isinstance(valor, bytes):
                    p[nome].write(valor)
                else:
                    p[nome].value = valor
        for nome, arr in (("u_luz_a", a), ("u_luz_cor", cor), ("u_luz_dir", dire), ("u_luz_cone", cone)):
            if nome in p:
                p[nome].write(arr.tobytes())

    def desenhar(self, malha_id: int, modelo: Optional[np.ndarray] = None) -> None:
        if not self.desenhou:
            self._comecar()
            self._uniformes()
            self._uniformes_do_quadro = id(self._iluminacao), id(self._estilo), self._vp.tobytes()
        elif self._uniformes_do_quadro != (id(self._iluminacao), id(self._estilo), self._vp.tobytes()):
            self._uniformes()
            self._uniformes_do_quadro = id(self._iluminacao), id(self._estilo), self._vp.tobytes()
        _, vao, n = self._malhas[malha_id]
        self._prog["u_modelo"].write(_mat(np.eye(4) if modelo is None else modelo))
        vao.render(moderngl.TRIANGLES, vertices=n)

    # ------------------------------------------------------------ saida
    def compor(self, destino: "moderngl.Framebuffer") -> None:
        """Amplia o quadro 3D para `destino` (a tela), com grao, vinheta e fita VHS."""
        destino.use()
        self._ctx.disable(moderngl.DEPTH_TEST)
        self._ctx.disable(moderngl.BLEND)
        self._quadro += 1
        q = self._quad_prog
        q["u_res"].value = tuple(float(x) for x in self._res_fbo)
        q["u_grao"].value = self._estilo.grao
        q["u_vinheta"].value = self._estilo.vinheta
        q["u_semente"].value = float(self._quadro % 997)
        q["u_vhs"].value = self._estilo.vhs
        q["u_espelhar"].value = 1.0 if self._estilo.espelhar else 0.0
        q["u_tempo"].value = self._quadro / 60.0
        self._cor.use(0)
        self._quad.render(moderngl.TRIANGLES)
        self.desenhou = False

    def compor_textura(self, textura: "moderngl.Texture") -> None:
        """Desenha uma textura RGBA por cima de tudo (a UI 2D), com transparencia."""
        self._ctx.disable(moderngl.DEPTH_TEST)
        self._ctx.enable(moderngl.BLEND)
        self._ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        q = self._quad_prog
        q["u_grao"].value = 0.0
        q["u_vinheta"].value = 0.0
        q["u_vhs"].value = 0.0
        q["u_espelhar"].value = 0.0
        textura.use(0)
        self._quad.render(moderngl.TRIANGLES)
        self._ctx.disable(moderngl.BLEND)

    def ler_pixels(self) -> np.ndarray:
        """O ultimo quadro 3D (antes de compor), (altura, largura, 3) uint8, de cima para baixo."""
        w, h = self._res_fbo
        dados = np.frombuffer(self._fbo.read(components=3), dtype=np.uint8).reshape(h, w, 3)
        return dados[::-1].copy()

    def liberar(self) -> None:
        for mid in list(self._malhas):
            self.remover_malha(mid)
        for obj in (self._fbo, self._cor, self._quad, self._quad_vbo, self._prog, self._quad_prog):
            if obj is not None:
                obj.release()
