"""
Parse Valor Batch Out CSV exports.
"""
from __future__ import annotations
import pandas as pd

REQUIRED = ["Transaction Date","Base Amount"]

def load_valor_csv(file) -> pd.DataFrame:
    df = pd.read_csv(file)
    missing=[c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")
    out=pd.DataFrame()
    out["transaction_time"]=pd.to_datetime(df["Transaction Date"], errors="coerce")
    out["amount"]=(df["Base Amount"].astype(str)
                   .str.replace("$","",regex=False)
                   .str.replace(",","",regex=False)
                   .astype(float))
    out["approval_code"]=df["Approval Code"] if "Approval Code" in df.columns else ""
    out["terminal"]=df["Device Label"] if "Device Label" in df.columns else ""
    return out.sort_values("transaction_time").reset_index(drop=True)
