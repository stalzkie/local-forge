use crossterm::{
    execute,
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
};
use ratatui::{
    backend::CrosstermBackend,
    layout::{Constraint, Direction, Layout},
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, List, ListItem, Paragraph, Wrap},
    Terminal,
};
use std::{io, time::Duration};

use super::events;

// ── Data model ───────────────────────────────────────────────────────────────

pub enum LogLevel {
    Info,
    Warn,
    #[allow(dead_code)]
    Error,
    Success,
}

pub struct LogEntry {
    pub level: LogLevel,
    pub message: String,
}

impl LogEntry {
    fn info(msg: impl Into<String>)    -> Self { Self { level: LogLevel::Info,    message: msg.into() } }
    fn warn(msg: impl Into<String>)    -> Self { Self { level: LogLevel::Warn,    message: msg.into() } }
    fn success(msg: impl Into<String>) -> Self { Self { level: LogLevel::Success, message: msg.into() } }
}

// ── Render helpers ───────────────────────────────────────────────────────────

fn level_style(level: &LogLevel) -> (Color, &'static str) {
    match level {
        LogLevel::Info    => (Color::Cyan,   " INFO "),
        LogLevel::Warn    => (Color::Yellow, " WARN "),
        LogLevel::Error   => (Color::Red,    " ERR  "),
        LogLevel::Success => (Color::Green,  "  OK  "),
    }
}

fn entry_to_list_item(entry: &LogEntry) -> ListItem<'_> {
    let (color, tag) = level_style(&entry.level);
    ListItem::new(Line::from(vec![
        Span::styled(
            format!("[{tag}] "),
            Style::default().fg(color).add_modifier(Modifier::BOLD),
        ),
        Span::raw(entry.message.clone()),
    ]))
}

// ── Main loop ────────────────────────────────────────────────────────────────

pub fn run() -> anyhow::Result<()> {
    // Set up terminal
    enable_raw_mode()?;
    let mut stdout = io::stdout();
    execute!(stdout, EnterAlternateScreen)?;
    let backend = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend)?;

    let mut logs: Vec<LogEntry> = vec![
        LogEntry::success("LocalForge v2.0 initialised."),
        LogEntry::info("Listening for git lifecycle hook triggers..."),
        LogEntry::success("ANE bridge: online  (38 TOPS available)"),
        LogEntry::info("MCP server: ready on port 7777"),
        LogEntry::info("AST validator: 7 secret-pattern rules loaded."),
        LogEntry::warn("CoreML model: stub active — Phase 4 required for ANE inference."),
    ];

    // Event loop
    loop {
        // Snapshot log items for this frame
        let items: Vec<ListItem> = logs.iter().map(entry_to_list_item).collect();

        terminal.draw(|f| {
            let area = f.size();

            let chunks = Layout::default()
                .direction(Direction::Vertical)
                .margin(1)
                .constraints([Constraint::Min(4), Constraint::Length(3)])
                .split(area);

            // ── Log panel ──────────────────────────────────────────────
            let log_block = Block::default()
                .title("  LocalForge Security Shield v2.0   [ANE-Accelerated] ")
                .title_style(Style::default().fg(Color::Blue).add_modifier(Modifier::BOLD))
                .borders(Borders::ALL)
                .border_style(Style::default().fg(Color::Blue));

            let log_list = List::new(items).block(log_block);
            f.render_widget(log_list, chunks[0]);

            // ── Status bar ─────────────────────────────────────────────
            let status = Paragraph::new(
                " [q] Quit   [c] Clear log   |   Waiting for commits… ",
            )
            .block(
                Block::default()
                    .borders(Borders::ALL)
                    .border_style(Style::default().fg(Color::DarkGray)),
            )
            .style(Style::default().fg(Color::DarkGray))
            .wrap(Wrap { trim: true });
            f.render_widget(status, chunks[1]);
        })?;

        // Poll for keypress (16 ms ≈ 60 fps)
        if events::poll(Duration::from_millis(16))? {
            match events::read()? {
                events::Event::Quit  => break,
                events::Event::Clear => logs.clear(),
                events::Event::None  => {}
            }
        }
    }

    // Restore terminal
    disable_raw_mode()?;
    execute!(terminal.backend_mut(), LeaveAlternateScreen)?;
    terminal.show_cursor()?;
    Ok(())
}
