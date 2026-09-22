import subprocess

print("Staging changes...")
subprocess.run(['git', 'add', '.'], check=True)

print("Committing changes...")
commit_msg = "fix: resolve silent update drop, remove invalid button styles, safe migrations, and start_polling updates"
subprocess.run(['git', 'commit', '-m', commit_msg], check=True)

print("Setting authenticated remote...")
token_remote = "https://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@github.com/playsiidona-bot/nexus-sells.git"
subprocess.run(['git', 'remote', 'set-url', 'origin', token_remote], check=True)

try:
    print("Pushing to main branch...")
    subprocess.run(['git', 'push', 'origin', 'main'], check=True)
    print("Successfully pushed to GitHub main!")
finally:
    print("Resetting remote URL...")
    subprocess.run(['git', 'remote', 'set-url', 'origin', 'https://github.com/playsiidona-bot/nexus-sells.git'], check=True)

print("Done!")
