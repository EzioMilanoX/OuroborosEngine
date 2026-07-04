"""Implementacao nula de IInputProvider: nunca captura input real do SO."""
from __future__ import annotations

from ouroboros.interfaces.input_provider import IInputProvider


class NullInputProvider(IInputProvider):
    """
    Implementacao nula de `IInputProvider`: nunca captura input real do
    SO. Testes (Pilar 5) injetam estado controlado atraves de metodos
    auxiliares de teste (fora do contrato desta ABC).
    """

    def __init__(self) -> None:
        self._staged_held = {}
        self._current_held = {}
        self._previous_held = {}
        self._axes = {}
        self._wants_quit = False

    def load_bindings(self, bindings_path: str) -> None:
        pass

    def poll(self) -> None:
        self._previous_held = dict(self._current_held)
        self._current_held = dict(self._staged_held)

    def is_action_pressed(self, action_name: str) -> bool:
        return self._current_held.get(action_name, False) and not self._previous_held.get(action_name, False)

    def is_action_held(self, action_name: str) -> bool:
        return self._current_held.get(action_name, False)

    def is_action_released(self, action_name: str) -> bool:
        return self._previous_held.get(action_name, False) and not self._current_held.get(action_name, False)

    def get_axis(self, axis_name: str) -> float:
        return self._axes.get(axis_name, 0.0)

    def wants_quit(self) -> bool:
        return self._wants_quit

    # -- metodos auxiliares de teste, fora do contrato de IInputProvider --

    def set_action_held(self, action_name: str, held: bool) -> None:
        """Programa `action_name` para ficar `held` a partir do proximo `poll()`."""
        self._staged_held[action_name] = held

    def set_axis(self, axis_name: str, value: float) -> None:
        """Define imediatamente o valor de `axis_name` (sem esperar `poll()`)."""
        self._axes[axis_name] = value

    def set_wants_quit(self, value: bool) -> None:
        """Programa `wants_quit()` para retornar `value`."""
        self._wants_quit = value
