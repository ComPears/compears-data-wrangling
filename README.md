# COMPEARS DATA SCRAPER

## Getting Started

Clone the project 
```
git clone https://github.com/ComPears/compears-data-wrangling.git
```

Enter the project directory 

```
cd compears-data-wrangling
```

Create a virtual env

```
python -m venv env 
```

Activate your env(for windows)

```
./env/Scripts/activate 	 
```
(for linux or mac)

```
source env/bin/activate 
``` 

Install Project Dependencies

```
python -m pip install -r requirements.txt
```



## ALDI
 To start scraping aldi
```
cd aldi
```

Run the main code
```
python3 main.py
```
#### Output should look like this 
![Image](https://github.com/user-attachments/assets/0bd97b85-312f-4536-b80d-5e7b10c45b10) <br/>

<br/>

> There should be a new aldi_results folder with all the json files extracted from the operation.

Navigate to the Test Folder

```
cd Test
```

Run the Merge file to Merge all the results together

```
python3 mergejson.py
```
#### Final Output for the merge operation
![Merged Json Screenshot](https://github.com/user-attachments/assets/4cdcce68-a269-43c2-b6b4-998730e7628f)


<br/>

Remove occurences of 'Boodschappenlijstje' by running the remove_boodsch file

```
python3 remove_boodsch.py
```

#### Final Output for the remove operation

![Screenshot 2025-05-24 at 18 30 50](https://github.com/user-attachments/assets/626858df-ba35-415c-9b19-851062121d3e)


Finally run the restructure file to restructure the document in the required format

```
python3 restructure.py
```
#### Final Output for the restructure operation
<img width="766" alt="Screenshot 2025-05-24 at 18 33 36" src="https://github.com/user-attachments/assets/c15d08be-c976-4d03-8d82-6b99cc1a7d44" />

## DIRK

cd into the dirk directory

```
cd DIRK
```
Run the main code 

```
python3 main.py
```
> All the scraped product should be in the dirk.json file

Run the seperate.py to seperate the products with offers based on the PROBEER PRIJS & ACTIE Keyword

```
python3 seperate.py
```

Output should look like this

<img width="756" alt="Screenshot 2025-05-25 at 19 56 57" src="https://github.com/user-attachments/assets/2928557d-4053-49b0-a17d-303a37b77b93" />


> The output file is the dirk_probeer_prijs_actie.json file

After this Run the actieprobeer.py file to restructure the offer products json file (dirk_probeer_prijs_actie.json) file

```
python3 actieprobeer.py
```
Then also run the structure py file to restructure the main dirk file

```
python3 structure.py
```



finally run the merge it file to merge the json file with offers with the structured dirk json file and the decimal fix py file to appropriately correct the point errors

```
python3 mergeit.py

```

```
python3 decimal_fix.py
```

> The final json file is the dirk_all.json file
>
> 

## JUMBO
cd into the Jumbo directory

```
cd JUMBO
```

Run the main file
```
python3 main.py
```

> All the scraped results are stored individually in the JSONs directory

After the main py file has been run, Run the merge file to merge all the seperate Json into a single one

```
python3 merge.py
```
Output should look like this
<img width="449" alt="Screenshot 2025-05-27 at 21 37 22" src="https://github.com/user-attachments/assets/80bd40fb-6cc4-49f3-bf90-07455be61728" />

> The merged raw jumbo json file is the Jumbo.json

After merging, run the structure.py file to restructure the results into the desired format

```
python3 structure.py
```
> The final output is the jumbo_all.json file






