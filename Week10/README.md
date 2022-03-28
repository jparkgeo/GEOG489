### Please copy and paste the following code to your Jupyter Notebook on CyberGISX. The code will download the materials for week 10.

!svn checkout https://github.com/jparkgeo/GEOG489/trunk/Week10

### If you run this code locally, you need to use the following commands for installing the necessary packages.

conda install --channel=conda-forge osmnx --y


### Install from the scratch.

conda create --name geog489 --y
conda activate geog489

conda install --channel conda-forge geopandas --y
conda install --channel conda-forge notebook --y
conda install --channel conda-forge esda --y
conda install tqdm –-y