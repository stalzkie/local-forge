pub mod dashboard;
mod events;

pub fn run_dashboard() -> anyhow::Result<()> {
    dashboard::run()
}
