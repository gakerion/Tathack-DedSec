import git

from driver import (
    create_commit,
    get_history,
    get_repo,
    get_repo_diff,
    get_repo_status,
    init_repo,
    stage_all,
    stage_files,
)


def print_menu() -> None:
    print("\nGit repository test menu")
    print("1. Initialize repository")
    print("2. Open repository")
    print("3. Show status")
    print("4. Show unstaged diff")
    print("5. Show staged diff")
    print("6. Stage selected files")
    print("7. Stage all files")
    print("8. Create commit")
    print("9. Show commit history")
    print("0. Exit")


def require_repo(repo: git.Repo | None) -> git.Repo:
    if repo is None:
        raise ValueError("Open or initialize a repository first.")

    return repo


def main() -> None:
    repo: git.Repo | None = None

    while True:
        print_menu()
        choice = input("Choose an option: ").strip()

        try:
            if choice == "0":
                print("Goodbye.")
                return

            if choice == "1":
                repo_path = input("Repository path: ").strip()
                repo = init_repo(repo_path)
                print(f"Repository initialized at: {repo.working_tree_dir}")

            elif choice == "2":
                repo_path = input("Repository path: ").strip()
                repo = get_repo(repo_path)
                print(f"Repository opened at: {repo.working_tree_dir}")

            elif choice == "3":
                print(require_repo(repo).git.status("--short", "--branch"))

            elif choice == "4":
                diff = get_repo_diff(require_repo(repo))
                print(diff or "No unstaged changes.")

            elif choice == "5":
                diff = get_repo_diff(require_repo(repo), staged=True)
                print(diff or "No staged changes.")

            elif choice == "6":
                paths = input(
                    "File paths, separated by commas: "
                ).split(",")
                file_paths = [path.strip() for path in paths if path.strip()]
                stage_files(require_repo(repo), file_paths)
                print("Selected files staged.")

            elif choice == "7":
                stage_all(require_repo(repo))
                print("All files staged.")

            elif choice == "8":
                message = input("Commit message: ")
                commit_hash = create_commit(require_repo(repo), message)
                print(f"Commit created: {commit_hash}")

            elif choice == "9":
                history = get_history(require_repo(repo))
                if not history:
                    print("No commits found.")
                else:
                    for commit in history:
                        print(f'{commit["hash"][:8]} {commit["message"]}')

            else:
                print("Invalid option. Choose a number from the menu.")

        except (
            FileNotFoundError,
            NotADirectoryError,
            ValueError,
            git.GitCommandError,
        ) as error:
            print(f"Error: {error}")


if __name__ == "__main__":
    main()