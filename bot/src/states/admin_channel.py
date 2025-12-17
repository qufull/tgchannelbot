from aiogram.fsm.state import StatesGroup, State


class SourceStates(StatesGroup):
    wait_channel = State()