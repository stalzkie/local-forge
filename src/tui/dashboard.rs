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

// ── Data model ────────────────────────────────────────────────────────────────

#[allow(dead_code)]
pub enum LogLevel {
    Info,
    Warn,
    Error,
    Success,
    Advisory,
}

pub struct LogEntry {
    pub level:   LogLevel,
    pub message: String,
}

impl LogEntry {
    pub fn info(msg: impl Into<String>)     -> Self { Self { level: LogLevel::Info,     message: msg.into() } }
    pub fn warn(msg: impl Into<String>)     -> Self { Self { level: LogLevel::Warn,     message: msg.into() } }
    #[allow(dead_code)]
    pub fn error(msg: impl Into<String>)    -> Self { Self { level: LogLevel::Error,    message: msg.into() } }
    pub fn success(msg: impl Into<String>)  -> Self { Self { level: LogLevel::Success,  message: msg.into() } }
    pub fn advisory(msg: impl Into<String>) -> Self { Self { level: LogLevel::Advisory, message: msg.into() } }
}

// ── Rendering helpers ─────────────────────────────────────────────────────────

fn level_color_tag(level: &LogLevel) -> (Color, &'static str) {
    match level {
        LogLevel::Info     => (Color::Cyan,    " INFO "),
        LogLevel::Warn     => (Color::Yellow,  " WARN "),
        LogLevel::Error    => (Color::Red,     " ERR  "),
        LogLevel::Success  => (Color::Green,   "  OK  "),
        LogLevel::Advisory => (Color::Magenta, " ADV  "),
    }
}

fn entry_to_list_item(entry: &LogEntry) -> ListItem<'_> {
    let (color, tag) = level_color_tag(&entry.level);
    ListItem::new(Line::from(vec![
        Span::styled(
            format!("[{tag}] "),
            Style::default().fg(color).add_modifier(Modifier::BOLD),
        ),
        Span::raw(entry.message.clone()),
    ]))
}

// ── Startup log entries ───────────────────────────────────────────────────────

fn startup_entries() -> Vec<LogEntry> {
    vec![
        LogEntry::success("LocalForge v2.0 initialised."),
        LogEntry::info("=== 3-Layer Hybrid Security Pipeline ==="),
        LogEntry::info("Layer 1 | Rust AST regex        — deterministic, <1 ms"),
        LogEntry::info("Layer 2 | CoreML classifier     — statistical,  ~200 ms  [ANE]"),
        LogEntry::info("Layer 3 | Qwen2.5-Coder-1.5B   — semantic,     ~5-10 s  [MLX]"),
        LogEntry::success("All layers online. Listening for git commits..."),
        LogEntry::info("MCP server: ready on port 7777"),
        LogEntry::warn("Layer 3 advisory is non-blocking — commits are never held for Qwen."),
        LogEntry::advisory("Advisory reports written to ~/.localforge/advisory_log/"),
    ]
}

// ── Advisory log reader ───────────────────────────────────────────────────────

fn load_recent_advisories(max: usize) -> Vec<LogEntry> {
    let log_dir = std::env::var("HOME")
        .map(std::path::PathBuf::from)
        .unwrap_or_else(|_| std::path::PathBuf::from("/tmp"))
        .join(".localforge/advisory_log");

    if !log_dir.exists() {
        return vec![];
    }

    let mut entries: Vec<(std::time::SystemTime, std::path::PathBuf)> = std::fs::read_dir(&log_dir)
        .ok()
        .into_iter()
        .flatten()
        .filter_map(|e| {
            let e = e.ok()?;
            let meta = e.metadata().ok()?;
            let modified = meta.modified().ok()?;
            Some((modified, e.path()))
        })
        .collect();

    entries.sort_by(|a, b| b.0.cmp(&a.0));

    entries.into_iter().take(max).filter_map(|(_, path)| {
        let content = std::fs::read_to_string(&path).ok()?;
        let json: serde_json::Value = serde_json::from_str(&content).ok()?;

        let severity = json["analysis"]["severity"].as_str().unwrap_or("unknown").to_uppercase();
        let summary  = json["analysis"]["summary"].as_str().unwrap_or("").to_string();
        let preview  = json["diff_preview"].as_str().unwrap_or("").to_string();
        let fname    = path.file_name()?.to_string_lossy().to_string();

        let level = match severity.as_str() {
            "HIGH"   => LogLevel::Error,
            "MEDIUM" => LogLevel::Warn,
            "LOW"    => LogLevel::Advisory,
            _        => LogLevel::Info,
        };

        Some(LogEntry {
            level,
            message: format!("[{severity}] {summary}  |  diff: {preview:.50}  |  {fname}"),
        })
    }).collect()
}

// ── Main loop ─────────────────────────────────────────────────────────────────

pub fn run() -> anyhow::Result<()> {
    enable_raw_mode()?;
    let mut stdout = io::stdout();
    execute!(stdout, EnterAlternateScreen)?;
    let backend = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend)?;

    let mut logs: Vec<LogEntry> = startup_entries();

    // Load any existing advisory reports on startup
    let recent = load_recent_advisories(5);
    if !recent.is_empty() {
        logs.push(LogEntry::info("--- Recent Qwen Advisories ---"));
        logs.extend(recent);
    }

    let mut tick: u64 = 0;

    loop {
        // Reload advisory reports every ~5 seconds (300 ticks × 16ms)
        tick += 1;
        if tick % 300 == 0 {
            let recent = load_recent_advisories(5);
            if !recent.is_empty() {
                logs.retain(|e| !matches!(e.level, LogLevel::Advisory)
                    || !e.message.starts_with('['));
                logs.push(LogEntry::info("--- Recent Qwen Advisories ---"));
                logs.extend(recent);
                // Keep last 200 entries
                if logs.len() > 200 {
                    logs.drain(0..logs.len() - 200);
                }
            }
        }

        let items: Vec<ListItem> = logs.iter().map(entry_to_list_item).collect();

        terminal.draw(|f| {
            let area = f.size();
            let chunks = Layout::default()
                .direction(Direction::Vertical)
                .margin(1)
                .constraints([Constraint::Min(4), Constraint::Length(3)])
                .split(area);

            // ── Main log panel ─────────────────────────────────────────────
            let log_block = Block::default()
                .title("  LocalForge Security Shield v2.0   [3-Layer Hybrid · ANE+MLX] ")
                .title_style(Style::default().fg(Color::Blue).add_modifier(Modifier::BOLD))
                .borders(Borders::ALL)
                .border_style(Style::default().fg(Color::Blue));

            f.render_widget(List::new(items).block(log_block), chunks[0]);

            // ── Status bar ─────────────────────────────────────────────────
            let status = Paragraph::new(
                " [q] Quit   [c] Clear log   |   L1:AST  L2:CoreML/ANE  L3:Qwen/MLX "
            )
            .block(Block::default().borders(Borders::ALL)
                .border_style(Style::default().fg(Color::DarkGray)))
            .style(Style::default().fg(Color::DarkGray))
            .wrap(Wrap { trim: true });
            f.render_widget(status, chunks[1]);
        })?;

        if events::poll(Duration::from_millis(16))? {
            match events::read()? {
                events::Event::Quit  => break,
                events::Event::Clear => {
                    logs.clear();
                    logs.extend(startup_entries());
                }
                events::Event::None  => {}
            }
        }
    }

    disable_raw_mode()?;
    execute!(terminal.backend_mut(), LeaveAlternateScreen)?;
    terminal.show_cursor()?;
    Ok(())
}
