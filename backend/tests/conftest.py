"""Pytest configuration and fixtures."""
import pytest


@pytest.fixture
def sample_preamble_html():
    """Sample merger agreement preamble HTML."""
    return """
    <html>
    <body>
    <p style="text-align:center"><b>AGREEMENT AND PLAN OF MERGER</b></p>
    <p>
    This Agreement and Plan of Merger (this "Agreement") is entered into as of
    January 15, 2024, by and among Alpha Holdings, Inc., a Delaware corporation
    ("Parent"), Alpha Merger Sub, Inc., a Delaware corporation and a wholly
    owned subsidiary of Parent ("Merger Sub"), and Target Company, Inc., a
    Delaware corporation (the "Company").
    </p>
    <p>
    RECITALS
    </p>
    <p>
    WHEREAS, the Board of Directors of the Company has determined that it is
    in the best interests of the Company and its stockholders for the Company
    to be acquired by Parent...
    </p>
    </body>
    </html>
    """


@pytest.fixture
def sample_sponsor_html():
    """Sample HTML with sponsor mention."""
    return """
    <html>
    <body>
    <p><b>FOR IMMEDIATE RELEASE</b></p>
    <p>
    Target Company, Inc. (NYSE: TGT) announced today that it has entered into
    a definitive agreement to be acquired by affiliates of Blackstone Inc.
    (NYSE: BX) in an all-cash transaction valued at approximately $5 billion.
    </p>
    <p>
    The acquisition will be funded through a combination of equity from funds
    managed by Blackstone and debt financing.
    </p>
    </body>
    </html>
    """


@pytest.fixture
def sample_underwriter_table_html():
    """Sample HTML with underwriter table."""
    return """
    <html>
    <body>
    <h3>UNDERWRITING</h3>
    <table border="1">
        <tr>
            <th>Underwriter</th>
            <th>Principal Amount</th>
        </tr>
        <tr>
            <td>J.P. Morgan Securities LLC</td>
            <td>$500,000,000</td>
        </tr>
        <tr>
            <td>Goldman Sachs & Co. LLC</td>
            <td>$500,000,000</td>
        </tr>
        <tr>
            <td>Bank of America Securities, Inc.</td>
            <td>$250,000,000</td>
        </tr>
        <tr>
            <td>Citigroup Global Markets Inc.</td>
            <td>$250,000,000</td>
        </tr>
    </table>
    </body>
    </html>
    """


@pytest.fixture
def sample_loan_syndicate_html():
    """Sample HTML with loan syndicate table."""
    return """
    <html>
    <body>
    <h3>CREDIT AGREEMENT</h3>
    <p>The following banks have committed to provide financing:</p>
    <table>
        <tr>
            <th>Lender</th>
            <th>Commitment</th>
            <th>Role</th>
        </tr>
        <tr>
            <td>JPMorgan Chase Bank, N.A.</td>
            <td>$1,000,000,000</td>
            <td>Administrative Agent and Joint Lead Arranger</td>
        </tr>
        <tr>
            <td>Bank of America, N.A.</td>
            <td>$750,000,000</td>
            <td>Syndication Agent and Joint Lead Arranger</td>
        </tr>
        <tr>
            <td>Wells Fargo Bank, N.A.</td>
            <td>$500,000,000</td>
            <td>Documentation Agent</td>
        </tr>
    </table>
    </body>
    </html>
    """
