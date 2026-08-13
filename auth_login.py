"""Automatic Samsung SSO login for the hub's shared Firefox profile."""
from browser_owner import request


def main():
    print(request("login"))


if __name__ == "__main__":
    main()
