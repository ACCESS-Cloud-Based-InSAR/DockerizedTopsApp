"""Download Sentinel-1 SLC granules from the Copernicus Data Space Ecosystem (CDSE).

This module provides an alternative to the ASF-based download in localize_slc.py.
It searches the CDSE OData catalog by granule name and downloads the product zip.

CDSE credentials (username/password) are required and can be provided via:
  - Environment variables: CDSE_USERNAME and CDSE_PASSWORD
  - The ~/.netrc file with machine: dataspace.copernicus.eu

References:
  - https://documentation.dataspace.copernicus.eu/APIs/OData.html
  - https://documentation.dataspace.copernicus.eu/APIs/Token.html
"""

import netrc
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

import requests
import tenacity
from tqdm import tqdm

CDSE_TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu"
    "/auth/realms/CDSE/protocol/openid-connect/token"
)
CDSE_ODATA_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
CDSE_DOWNLOAD_URL = "https://download.dataspace.copernicus.eu/odata/v1/Products"


def get_cdse_credentials(
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> tuple[str, str]:
    """Resolve CDSE credentials from arguments, environment, or ~/.netrc.

    Parameters
    ----------
    username : str, optional
        CDSE username. Falls back to CDSE_USERNAME env var, then ~/.netrc.
    password : str, optional
        CDSE password. Falls back to CDSE_PASSWORD env var, then ~/.netrc.

    Returns
    -------
    tuple[str, str]
        (username, password)
    """
    if username and password:
        return username, password

    # Try environment variables
    env_user = os.getenv("CDSE_USERNAME")
    env_pass = os.getenv("CDSE_PASSWORD")
    if env_user and env_pass:
        return env_user, env_pass

    # Try ~/.netrc
    try:
        nrc = netrc.netrc()
        auth = nrc.authenticators("dataspace.copernicus.eu")
        if auth:
            return auth[0], auth[2]
    except (FileNotFoundError, netrc.NetrcParseError):
        pass

    raise ValueError(
        "CDSE credentials not found. Provide them via:\n"
        "  1. username/password arguments\n"
        "  2. CDSE_USERNAME and CDSE_PASSWORD environment variables\n"
        "  3. ~/.netrc entry for machine dataspace.copernicus.eu"
    )


CDSE_HOST = "dataspace.copernicus.eu"


def ensure_cdse_credentials(
    username: Optional[str] = None,
    password: Optional[str] = None,
    host: str = CDSE_HOST,
) -> None:
    """Ensure CDSE credentials are available in ~/.netrc.

    This mirrors the behavior of ensure_earthdata_credentials() for consistency.
    CDSE username and password may be provided by, in order of preference:
       * ``username`` and ``password`` arguments
       * ``CDSE_USERNAME`` and ``CDSE_PASSWORD`` environment variables
       * ``~/.netrc`` entry for machine dataspace.copernicus.eu

    If credentials are provided via arguments or env vars but ~/.netrc does not
    contain an entry for CDSE, the entry will be appended to ~/.netrc.

    Parameters
    ----------
    username : str, optional
        CDSE username (email).
    password : str, optional
        CDSE password.
    host : str
        The netrc machine name (default: dataspace.copernicus.eu).

    Raises
    ------
    ValueError
        If no valid credentials can be resolved.
    """
    if username is None:
        username = os.getenv("CDSE_USERNAME")
    if password is None:
        password = os.getenv("CDSE_PASSWORD")

    netrc_file = Path.home() / ".netrc"

    # Check if netrc already has CDSE credentials
    cdse_in_netrc = False
    if netrc_file.exists():
        try:
            nrc = netrc.netrc(netrc_file)
            if nrc.authenticators(host):
                cdse_in_netrc = True
        except netrc.NetrcParseError:
            pass

    # If we have credentials but they're not in netrc, append them
    if username and password and not cdse_in_netrc:
        with open(netrc_file, "a") as f:
            f.write(f"\nmachine {host} login {username} password {password}\n")
        netrc_file.chmod(0o600)

    # Now verify we can get credentials
    try:
        get_cdse_credentials(username, password)
    except ValueError:
        raise ValueError(
            f"Please provide valid CDSE credentials via {netrc_file}, "
            f"username and password options, or "
            f"the CDSE_USERNAME and CDSE_PASSWORD environment variables."
        )


def get_cdse_access_token(username: str, password: str) -> str:
    """Obtain an access token from the CDSE identity provider.

    Parameters
    ----------
    username : str
        CDSE account email/username.
    password : str
        CDSE account password.

    Returns
    -------
    str
        Bearer access token.
    """
    data = {
        "grant_type": "password",
        "username": username,
        "password": password,
        "client_id": "cdse-public",
    }

    response = requests.post(CDSE_TOKEN_URL, data=data, timeout=60)
    response.raise_for_status()
    return response.json()["access_token"]


def search_cdse_by_granule_name(granule_name: str) -> dict:
    """Search the CDSE OData catalog for a Sentinel-1 SLC by granule name.

    The granule_name should be the ASF-style scene name, e.g.:
        S1A_IW_SLC__1SDV_20220212T222803_20220212T222830_041886_04FCA3_2B3E

    CDSE stores products with a ``.SAFE`` suffix, so we append it for the query.

    Parameters
    ----------
    granule_name : str
        Sentinel-1 granule / scene name (without .SAFE or .zip extension).

    Returns
    -------
    dict
        Product entry from the CDSE OData response containing at least ``Id``
        and ``Name`` fields.

    Raises
    ------
    LookupError
        If the product is not found on CDSE.
    """
    # Strip extensions if caller accidentally included them
    granule_name = granule_name.replace(".zip", "").replace(".SAFE", "")

    safe_name = f"{granule_name}.SAFE"
    query = f"{CDSE_ODATA_URL}?$filter=Name eq '{safe_name}'"

    response = requests.get(query, timeout=120)
    response.raise_for_status()
    results = response.json().get("value", [])

    if not results:
        raise LookupError(
            f"Product '{safe_name}' not found in CDSE catalog. Query: {query}"
        )

    # Return the first match (there should be exactly one for a unique granule name)
    return results[0]


def download_single_slc_from_cdse(
    granule_name: str,
    access_token: str,
    output_dir: str = ".",
    max_retries: int = 3,
) -> str:
    """Download a single Sentinel-1 SLC product from CDSE.

    Parameters
    ----------
    granule_name : str
        Sentinel-1 granule / scene name.
    access_token : str
        CDSE bearer access token.
    output_dir : str
        Directory to save the downloaded zip file.
    max_retries : int
        Number of download attempts before raising an error.

    Returns
    -------
    str
        The filename of the downloaded zip file (e.g., ``<granule_name>.zip``).
    """
    granule_name = granule_name.replace(".zip", "").replace(".SAFE", "")

    # Search for the product to get its UUID
    product = search_cdse_by_granule_name(granule_name)
    product_id = product["Id"]

    download_url = f"{CDSE_DOWNLOAD_URL}({product_id})/$zip"
    headers = {"Authorization": f"Bearer {access_token}"}

    out_filename = f"{granule_name}.zip"
    out_path = Path(output_dir) / out_filename

    def _before(retry_state: tenacity.RetryCallState) -> None:
        print(f"CDSE download attempt #{retry_state.attempt_number} for {granule_name}")

    def _before_sleep(retry_state: tenacity.RetryCallState) -> None:
        wait = retry_state.next_action.sleep  # type: ignore[union-attr]
        print(
            f"Attempt #{retry_state.attempt_number} failed: {retry_state.outcome.exception()}"
        )
        print(f"Waiting {wait:.0f}s before retry...")

    @tenacity.retry(
        reraise=True,
        stop=tenacity.stop_after_attempt(max_retries),
        wait=tenacity.wait_incrementing(start=10, increment=10),
        retry=tenacity.retry_if_exception_type(requests.RequestException),
        before=_before,
        before_sleep=_before_sleep,
    )
    def _attempt_download() -> str:
        try:
            response = requests.get(
                download_url,
                headers=headers,
                stream=True,
                timeout=600,
            )
            response.raise_for_status()

            with open(out_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192 * 16):
                    if chunk:
                        f.write(chunk)

            if out_path.stat().st_size == 0:
                out_path.unlink(missing_ok=True)
                raise requests.RequestException("Downloaded file is empty")

            print(
                f"Successfully downloaded {out_filename} from CDSE ({out_path.stat().st_size / 1e6:.1f} MB)"
            )
            return out_filename
        except requests.RequestException:
            out_path.unlink(missing_ok=True)
            raise

    return _attempt_download()


def download_slcs_from_cdse(
    slc_ids: list[str],
    username: Optional[str] = None,
    password: Optional[str] = None,
    output_dir: str = ".",
    max_workers: int = 3,
    dry_run: bool = False,
) -> list[str]:
    """Download multiple Sentinel-1 SLC granules from CDSE.

    Parameters
    ----------
    slc_ids : list[str]
        List of Sentinel-1 granule / scene names.
    username : str, optional
        CDSE username. Resolved from env/netrc if not provided.
    password : str, optional
        CDSE password. Resolved from env/netrc if not provided.
    output_dir : str
        Directory to save downloaded zip files.
    max_workers : int
        Number of parallel download threads.
    dry_run : bool
        If True, only search CDSE (verify product exists) but skip download.

    Returns
    -------
    list[str]
        List of downloaded zip filenames.
    """
    cdse_user, cdse_pass = get_cdse_credentials(username, password)
    access_token = get_cdse_access_token(cdse_user, cdse_pass)

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    if dry_run:
        filenames = []
        for slc_id in slc_ids:
            product = search_cdse_by_granule_name(slc_id)
            fname = slc_id.replace(".zip", "").replace(".SAFE", "") + ".zip"
            print(f"[dry-run] Found on CDSE: {product['Name']} (Id={product['Id']})")
            filenames.append(fname)
        return filenames

    def _download_one(slc_id):
        return download_single_slc_from_cdse(
            slc_id,
            access_token=access_token,
            output_dir=output_dir,
        )

    n = len(slc_ids)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(
            tqdm(
                executor.map(_download_one, slc_ids),
                total=n,
                desc="Downloading SLCs from CDSE",
            )
        )

    return results
