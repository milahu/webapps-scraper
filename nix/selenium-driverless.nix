{
  lib,
  python,
  fetchFromGitHub,
  cdp-socket,
}:

python.pkgs.buildPythonPackage rec {
  pname = "selenium-driverless";
  version = "unstable-2024-10-30";
  pyproject = true;

  src = fetchFromGitHub {
    owner = "kaliiiiiiiiii";
    repo = "Selenium-Driverless";
    # https://github.com/kaliiiiiiiiii/Selenium-Driverless/tree/dev
    rev = "fb2339a3311334ec6b05ec33232570fb2e4af6ba";
    hash = "sha256-s319wsR6HS47WBAD8uwa3crvARzRfGImKjfohOgN9Hk=";
  };

  build-system = [
    python.pkgs.setuptools
    python.pkgs.wheel
  ];

  dependencies = with python.pkgs; [
    # aiodebug
    aiofiles
    aiohttp
    # cdp-patches
    cdp-socket
    jsondiff
    matplotlib
    numpy
    platformdirs
    pytest
    pytest-asyncio
    pytest-subtests
    scipy
    selenium
    setuptools
    sphinx
    sphinx-autodoc-typehints
    sphinx-rtd-theme
    twine
    typing-extensions
    websockets
  ];

  pythonImportsCheck = [
    "selenium_driverless"
  ];

  meta = with lib; {
    description = "A stealthy browser automation framework";
    homepage = "https://github.com/kaliiiiiiiiii/Selenium-Driverless";
    license = licenses.cc-by-nc-sa-40;
    maintainers = with lib.maintainers; [ ];
  };
}
