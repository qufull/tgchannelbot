

from aiogram.fsm.state import StatesGroup, State


class AdminStates(StatesGroup):
    wait_source_link = State()
    wait_target_forward = State()