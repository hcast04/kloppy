from dataclasses import replace, dataclass
from typing import Optional, List, Type
from kloppy.domain import (
    Event,
    Team,
    EventDataset,
    PassEvent,
    CarryEvent,
    RecoveryEvent,
    BallOutEvent,
    FoulCommittedEvent,
    ShotEvent,
    DuelEvent,
    TakeOnEvent,
    GoalkeeperEvent,
    InterceptionEvent,
    Qualifier,
    SetPieceQualifier,
    EventType,
    PassResult,
    ShotResult,
    DuelResult,
    InterceptionResult,
)
from ..builder import StateBuilder


@dataclass
class Possesion:
    sequence_id: int
    team: Optional[Team]
    previous_event_type: Optional[Type[Event]] = None
    previous_event_outcome: Optional[bool] = None


class PossesionStateBuilder(StateBuilder):
    dataSet : EventDataset
    next_event: Optional[Event]

    def __init__(self):
        """
            EventType.PERIOD_START,
            EventType.PERIOD_END,
            EventType.LINEUP,
            """
        self.off_ball_events = [
            
            EventType.SUBSTITUTION
        ]
        super().__init__()

    def initial_state(self, dataset: EventDataset) -> Possesion:
        self.dataSet = dataset
        return Possesion(sequence_id=0, team=None)

    def _is_off_ball_event(self, event: Event) -> bool:
        
        if hasattr(event, 'event_type'):
            return event.event_type in self.off_ball_events
        return False

    def _is_set_piece(self, event: Event) -> bool:
        
        if hasattr(event, 'qualifiers') and event.qualifiers is not None:
            for qualifier in event.qualifiers:
                if isinstance(qualifier, SetPieceQualifier):
                    return True
        return False

    def _is_failed_pass(self, event: Event) -> bool:
        
        if isinstance(event, PassEvent):
            return event.result == PassResult.INCOMPLETE
        return False

    def _is_successful_interception(self, event: Event) -> bool:
        
        if isinstance(event, InterceptionEvent):
            return event.result == InterceptionResult.SUCCESS
        return False

    def _is_goalkeeper_claim(self, event: Event) -> bool:
        
        if isinstance(event, GoalkeeperEvent):
            return hasattr(event, 'goalkeeper_action') and event.goalkeeper_action in [
                'claim', 'pick_up', 'save'
            ]
        return False

    def _is_rebound(self, event: Event, next_event: Optional[Event] = None) -> bool:
        
        if isinstance(event, ShotEvent) and event.result != ShotResult.GOAL:
            if next_event and hasattr(next_event, 'timestamp') and hasattr(event, 'timestamp'):
                time_diff = next_event.timestamp - event.timestamp
                return (time_diff.total_seconds() < 3 and
                        isinstance(next_event, (ShotEvent, PassEvent)) and
                        next_event.team == event.team)
        return False

    def can_start_sequence(self, event: Event) -> bool:
        
        if self._is_off_ball_event(event):
            return False

        return (isinstance(event, (PassEvent, CarryEvent, RecoveryEvent, TakeOnEvent)) or
                self._is_goalkeeper_claim(event) or
                self._is_successful_interception(event))
    


    def reduce_before(self, state: Possesion, event: Event) -> Possesion:
        
        if self._is_off_ball_event(event):
            return state

        events = self.dataSet.events
        event_index = events.index(event) if event in events else -1
        self.next_event = events[event_index + 1] if 0 <= event_index and event_index < len(events) - 1 else None

        should_start_new_sequence = self.can_start_sequence(event)

        if should_start_new_sequence:
            if state.team != event.team or self._is_set_piece(event):
                should_start_new_sequence = True
            elif isinstance(event, TakeOnEvent) and getattr(event, 'result', True):
                should_start_new_sequence = True

            if isinstance(event, DuelEvent) and event.result == DuelResult.WON and state.previous_event_type == DuelEvent and state.previous_event_outcome == DuelResult.LOST:
                should_start_new_sequence = True

            if self._is_failed_pass(event) and state.team == event.team:
                should_start_new_sequence = False

            elif should_start_new_sequence:
                state = replace(
                    state,
                    sequence_id=state.sequence_id + 1,
                    team=event.team
                )

        return self.reduce_after(state, event)


    def reduce_after(self, state: Possesion, event: Event) -> Possesion:
        state = replace(
            state,
            previous_event_type=type(event),
            previous_event_outcome=getattr(event, 'outcome', None)
        )

        if isinstance(event, (BallOutEvent, FoulCommittedEvent)):
            return replace(state, sequence_id=state.sequence_id + 1, team=None)

        if isinstance(event, ShotEvent) and not self._is_rebound(event, self.next_event):
            return replace(state, sequence_id=state.sequence_id + 1, team=None)

        if isinstance(event, DuelEvent):
            if event.result == DuelResult.LOST and not (state.previous_event_type == DuelEvent and state.previous_event_outcome == DuelResult.WON):
                return replace(state, sequence_id=state.sequence_id + 1, team=None)

        return state
