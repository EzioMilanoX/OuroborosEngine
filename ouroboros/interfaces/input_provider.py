"""Contrato de captura de input (IInputProvider), abstraido por nome de acao data-driven."""
from __future__ import annotations

from abc import ABC, abstractmethod


class IInputProvider(ABC):
    """
    Contrato de captura de input. O nucleo/produtos so conhecem NOMES
    de acao (`str`), carregados de bindings JSON data-driven -- nunca
    codigos de tecla/botao especificos de um backend (nada de
    `pygame.K_SPACE` vazando para fora de `ouroboros.adapters`).
    """

    @abstractmethod
    def load_bindings(self, bindings_path: str) -> None:
        """Carrega o mapeamento acao -> tecla/botao fisico a partir de um arquivo JSON de bindings."""
        ...

    @abstractmethod
    def poll(self) -> None:
        """
        Consome a fila de eventos nativos do backend concreto e
        atualiza o ESTADO INTERNO (arrays/flags primitivos ja
        pre-alocados na implementacao concreta). Chamado no maximo uma
        vez por frame pelo laco principal; NAO retorna nem constroi
        nenhum objeto de snapshot novo -- as consultas de estado abaixo
        leem esse estado interno ja atualizado.
        """
        ...

    @abstractmethod
    def is_action_pressed(self, action_name: str) -> bool:
        """True no frame em que `action_name` transicionou de solto para pressionado."""
        ...

    @abstractmethod
    def is_action_held(self, action_name: str) -> bool:
        """True enquanto `action_name` permanece pressionado, independente de borda."""
        ...

    @abstractmethod
    def is_action_released(self, action_name: str) -> bool:
        """True no frame em que `action_name` transicionou de pressionado para solto."""
        ...

    @abstractmethod
    def get_axis(self, axis_name: str) -> float:
        """Valor continuo `[-1.0, 1.0]` de um eixo (analogico, D-pad, WASD combinado, etc.)."""
        ...

    @abstractmethod
    def wants_quit(self) -> bool:
        """True se o backend recebeu um pedido nativo de encerramento da aplicacao."""
        ...
