### Please copy and paste the following code to your Jupyter Notebook on CyberGISX. The code will download the materials for week 10.

!svn checkout https://github.com/jparkgeo/GEOG489/trunk/Week10

### If you run this code locally, you need to use the following commands for installing the necessary packages.

conda install --channel=conda-forge osmnx --y


### Install from the scratch.

conda create --name geog489 --y <br>
conda activate geog489 <br>

conda install --channel conda-forge geopandas --y <br>
conda install --channel=conda-forge osmnx --y <br>
conda install --channel conda-forge notebook --y <br>
conda install --channel conda-forge esda --y <br>
conda install tqdm –-y <br>
