# COMPEARS DATA SCRAPER

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



# ALDI
 To start scraping aldi
```
cd aldi
```

Run the main code
```
python3 main.py
```
### It should look like this 
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
### Final Output for the merge operation
![Merged Json Screenshot](https://github.com/user-attachments/assets/4cdcce68-a269-43c2-b6b4-998730e7628f)






