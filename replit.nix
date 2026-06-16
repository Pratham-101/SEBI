{ pkgs }: {
  deps = [
    pkgs.python311
    pkgs.python311Packages.pip
    # System libraries Playwright/Chromium needs at runtime.
    pkgs.glib
    pkgs.nss
    pkgs.nspr
    pkgs.dbus
    pkgs.atk
    pkgs.at-spi2-atk
    pkgs.at-spi2-core
    pkgs.cups
    pkgs.libdrm
    pkgs.gtk3
    pkgs.pango
    pkgs.cairo
    pkgs.libxkbcommon
    pkgs.mesa
    pkgs.expat
    # Specifically named by Playwright's host-deps check on Replit:
    pkgs.gdk-pixbuf
    pkgs.freetype
    pkgs.fontconfig
    pkgs.xorg.libXrender
    pkgs.xorg.libX11
    pkgs.xorg.libXcomposite
    pkgs.xorg.libXcursor
    pkgs.xorg.libXdamage
    pkgs.xorg.libXext
    pkgs.xorg.libXfixes
    pkgs.xorg.libXi
    pkgs.xorg.libXrandr
    pkgs.xorg.libXtst
    pkgs.xorg.libxcb
    pkgs.alsa-lib
  ];
}
