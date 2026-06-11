import pandas as pd
import difflib

df = pd.read_csv("samples.csv")
out = pd.read_csv("output.csv")

correct = 0

for _, row in df.iterrows():

    buggy = row["Code"].split("\n")
    fixed = row["Correct Code"].split("\n")

    actual = []

    for i,(a,b) in enumerate(zip(buggy,fixed),1):
        if a != b:
            actual.append(i)

    pred = int(
        out[out["ID"]==row["ID"]]["Bug Line"].iloc[0]
    )

    if pred in actual:
        correct += 1

print("Accuracy:", correct/len(df)*100,"%")