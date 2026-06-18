use crossterm::event::{self, Event as CEvent, KeyCode};
use std::time::Duration;

pub enum Event {
    Quit,
    Clear,
    None,
}

pub fn poll(timeout: Duration) -> anyhow::Result<bool> {
    Ok(event::poll(timeout)?)
}

pub fn read() -> anyhow::Result<Event> {
    if let CEvent::Key(key) = event::read()? {
        return Ok(match key.code {
            KeyCode::Char('q') | KeyCode::Char('Q') | KeyCode::Esc => Event::Quit,
            KeyCode::Char('c') | KeyCode::Char('C')                 => Event::Clear,
            _                                                         => Event::None,
        });
    }
    Ok(Event::None)
}
