class Localforge < Formula
  desc "Rust-native AI security gateway that reviews your code before git does"
  homepage "https://github.com/stalzkie/local-forge"
  version "2.0.0"

  on_arm do
    url "https://github.com/stalzkie/local-forge/releases/download/v2.0.0/localforge-v2.0.0-aarch64-apple-darwin.tar.gz"
    sha256 "6b12c3fb199c143811054a097780297872fa50433cb5e931f583915795a03ae6"
  end

  # Runtime Python deps for Layer 2 (CoreML) and Layer 3 (Qwen advisory)
  depends_on "python@3.11" => :recommended

  def install
    bin.install "localforge"
    # Ship the Python shims alongside the binary
    (share/"localforge/coreml").mkpath
    (share/"localforge/coreml").install "coreml/infer.py"
    (share/"localforge/coreml").install "coreml/advisory.py"
    # Ship the pre-commit hook template
    (share/"localforge").install "hooks/pre-commit"
  end

  def post_install
    # Create ~/.localforge directory structure so first run succeeds
    lf_dir = Pathname.new(ENV["HOME"]) / ".localforge"
    (lf_dir / "bin").mkpath
    (lf_dir / "coreml").mkpath
    (lf_dir / "reports").mkpath

    # Symlink binary into ~/.localforge/bin so the hook finds it at its canonical path
    lf_bin = lf_dir / "bin" / "localforge"
    lf_bin.unlink if lf_bin.exist?
    lf_bin.make_symlink(bin / "localforge")

    # Copy shims
    (lf_dir / "coreml" / "infer.py").write (share / "localforge/coreml/infer.py").read \
      unless (lf_dir / "coreml" / "infer.py").exist?
    (lf_dir / "coreml" / "advisory.py").write (share / "localforge/coreml/advisory.py").read \
      unless (lf_dir / "coreml" / "advisory.py").exist?
  end

  def caveats
    <<~EOS
      LocalForge requires two additional setup steps after install:

      1. Build the CoreML model (Layer 2 — one-time):
           pip3 install coremltools scikit-learn numpy
           python3 #{share}/localforge/coreml/infer.py  # (or run build_model.py from the repo)

      2. Enable Qwen code review (Layer 3 — optional):
           pip3 install mlx-lm
           python3 -c "from mlx_lm import load; load('Qwen/Qwen2.5-Coder-1.5B-Instruct-4bit')"

      3. Install the hook into any git repo:
           localforge --install /path/to/your/repo

      LocalForge binary is symlinked to ~/.localforge/bin/localforge so the
      pre-commit hook finds it even without modifying PATH.
    EOS
  end

  test do
    # Verify the binary runs and detects a known AWS key pattern
    fake_key = "AKIA" + "IOSFODNN7EXAMPLE"
    output = shell_output("echo '+aws_token = #{fake_key}' | #{bin}/localforge --scan", 1)
    assert_match "BLOCKED", output
  end
end
