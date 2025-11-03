import pandas as pd
import numpy as np
from io import StringIO

# Complete CSV data from the file
csv_data = """Recipe_Name,Cuisine_Type,Difficulty_Level,Cooking_Time_Min,Prep_Time_Min,Servings,Main_Ingredient,Cooking_Method,Dietary_Category,Calories_Per_Serving
Recipe_1,Italian,Medium,30,53,8,Mushrooms,Braising,Vegan,744
Recipe_2,American,Medium,51,11,6,Pasta,Stir-fry,Regular,386
Recipe_3,Japanese,Hard,62,15,7,Tofu,Steaming,Keto,746
Recipe_4,French,Hard,90,25,2,Vegetables,Sauteing,Keto,287
Recipe_5,Asian,Hard,38,52,8,Beef,Baking,Vegan,506
Recipe_6,Mexican,Medium,100,34,6,Pork,Stir-fry,Low-Carb,447
Recipe_7,Indian,Hard,117,19,5,Rice,Sauteing,Low-Carb,345
Recipe_8,Asian,Easy,113,34,3,Beef,Roasting,Low-Carb,471
Recipe_9,Indian,Hard,84,36,6,Pasta,Frying,Gluten-Free,351
Recipe_10,Italian,Easy,25,26,6,Vegetables,Stir-fry,Gluten-Free,273
Recipe_11,Japanese,Easy,79,11,2,Fish,Stir-fry,Keto,547
Recipe_12,Thai,Easy,91,54,5,Fish,Baking,Gluten-Free,276
Recipe_13,Asian,Medium,39,47,5,Chicken,Braising,Low-Carb,390
Recipe_14,American,Easy,105,29,5,Rice,Baking,Regular,552
Recipe_15,Japanese,Medium,87,34,2,Tofu,Grilling,Vegetarian,474
Recipe_16,Thai,Hard,108,45,7,Vegetables,Sauteing,Paleo,434
Recipe_17,Japanese,Hard,30,20,5,Mushrooms,Grilling,Low-Carb,685
Recipe_18,Japanese,Easy,116,42,8,Beef,Braising,Vegetarian,279
Recipe_19,French,Hard,112,16,6,Pasta,Stir-fry,Low-Carb,539
Recipe_20,Thai,Easy,76,19,7,Lentils,Sauteing,Keto,437
Recipe_21,Korean,Medium,65,28,4,Pork,Grilling,Gluten-Free,512
Recipe_22,Greek,Easy,45,15,2,Chicken,Baking,Mediterranean,398
Recipe_23,Lebanese,Medium,75,35,6,Lamb,Stewing,Gluten-Free,456
Recipe_24,Southern,Hard,120,45,3,Pork,Smoking,Low-Carb,678
Recipe_25,Vietnamese,Easy,30,20,5,Shrimp,Stir-fry,Low-Carb,289
Recipe_26,Moroccan,Medium,85,40,4,Chicken,Tagine,Gluten-Free,423
Recipe_27,German,Hard,95,50,6,Beef,Braising,Low-Carb,567
Recipe_28,Peruvian,Medium,70,25,4,Fish,Ceviche,Gluten-Free,334
Recipe_29,Jamaican,Easy,55,30,3,Chicken,Steaming,Gluten-Free,412
Recipe_30,Eastern European,Hard,140,60,2,Pork,Roasting,Low-Carb,789
Recipe_31,Spanish,Medium,80,35,5,Rice,Paella,Gluten-Free,445
Recipe_32,Caribbean,Easy,40,18,4,Fish,Grilling,Gluten-Free,356
Recipe_33,Ethiopian,Medium,65,42,6,Lentils,Stewing,Vegan,298
Recipe_34,Turkish,Hard,110,38,3,Lamb,Grilling,Gluten-Free,623
Recipe_35,Polish,Medium,90,45,5,Pasta,Boiling,Low-Carb,478
Recipe_36,Easy,50,22,4,Pork,Roasting,Gluten-Free,389
Recipe_37,Swedish,Hard,105,48,2,Fish,Smoking,Low-Carb,534
Recipe_38,Portuguese,Medium,75,33,4,Seafood,Steaming,Gluten-Free,367
Recipe_39,Hungarian,Hard,125,55,3,Beef,Braising,Low-Carb,689
Recipe_40,Israeli,Easy,35,25,5,Chickpeas,Sauteing,Vegan,312
