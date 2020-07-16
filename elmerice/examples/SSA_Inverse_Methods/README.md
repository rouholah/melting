# SSA inverse methods test cases

This test cases for the adjoint inverse methods using the SSA have been updated 
in April 2020 from the material presented for the 
[Elmer/Ice course](http://elmerfem.org/elmerice/wiki/doku.php?id=courses:courses) held in Oslo in 2016.

The description of the test cases can be found in the associated presentation available [here](
http://elmerfem.org/elmerice/wiki/lib/exe/fetch.php?media=courses:2016_oslo_shallow_inverse.pdf).
Note that the solvers have been updated so that the implementation differs and use the new solvers 
for the inverse methods (see documentation [here](https://github.com/ElmerCSC/elmerfem/tree/elmerice/elmerice/Solvers/Documentation)).

- Content of this directory:

   - DATA: data sets and processing tools required to run the experiments.  
   - src: user functions needed by the test cases.  
   - SCRIPTS: python scripts used for post-processing.

   - MacAyeal: Optimisation of the basal friction coefficient based on a synthetic test case.
   - RonneFilchner: Optimisation of the viscosity on the Ronne-Filchner ice-shelf. You will need data-sets to run this experiment, see in the DATA directory.
