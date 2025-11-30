import pandas as pd
from pandas import DataFrame
from quantulum3 import parser
import unit_parse

def print_nutrition_dataframe(nutrition: DataFrame):
    for index, row in nutrition.iterrows():
        #print(row)
        print(f'{row['description']}\n\t{row['calories_per_dollar']}')

nutrition: DataFrame = pd.read_csv('./kroger_all_nutrition.csv')

# add column for calories per dollar
nutrition['calories_per_dollar'] = 0

drop_indexes = []
for index, row in nutrition.iterrows():
    calories_per_dollar = float(row['calories']) / float(row['price'])

    if not pd.isna(row['servings_per_package']):
        nutrition.at[index, 'calories_per_dollar'] = (float(row['calories']) * float(row['servings_per_package'])) / float(row['price'])
    elif not pd.isna(row['size']) and not pd.isna(row['serving_size']):
        try:
            # Raw dog conversion
            size = parser.parse(row['size'])[0]
            serving_size = parser.parse(row['serving_size'])[0]

            # To pint
            size = f"{size.value} {size.unit.symbols[0]}"
            size = unit_parse.parser(str(size))
            serving_size = f"{serving_size.value} {serving_size.unit.symbols[0]}"
            serving_size = unit_parse.parser(str(serving_size))

            serving_size = serving_size.to(size.units)

            ratio = (size / serving_size)
            calories_per_dollar = (float(row['calories']) * (ratio)) / float(row['price'])

            nutrition.at[index, 'calories_per_dollar'] = calories_per_dollar
        except Exception as e:
            pass

for i in drop_indexes:
    nutrition.drop(i, inplace=True)

nutrition.sort_values(by='calories_per_dollar', ascending=False, inplace=True)

print_nutrition_dataframe(nutrition)

