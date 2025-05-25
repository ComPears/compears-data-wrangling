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

Run the seperate.py to seperate the products with offers

```
python3 seperate.py
```

Output should look like this













