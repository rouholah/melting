SET(arpack_SRCS cgetv0.f cnaitr.f cnapps.f cnaup2.f cnaupd.f cneigh.f
	cneupd.f cngets.f csortc.f cstatn.f debug.h dgetv0.f dlaqrb.f
	dnaitr.f dnapps.f dnaup2.f dnaupd.f dnconv.f dneigh.f dneupd.f
	dngets.f dsaitr.f dsapps.f dsaup2.f dsaupd.f dsconv.f dseigt.f
	dsesrt.f dseupd.f dsgets.f dsortc.f dsortr.f dstatn.f dstats.f
	dstqrb.f sgetv0.f slaqrb.f snaitr.f snapps.f snaup2.f snaupd.f
	snconv.f sneigh.f sneupd.f sngets.f ssaitr.f ssapps.f ssaup2.f
	ssaupd.f ssconv.f sseigt.f ssesrt.f sseupd.f ssgets.f ssortc.f
	ssortr.f sstatn.f sstats.f sstqrb.f stat.h version.h zgetv0.f
	znaitr.f znapps.f znaup2.f znaupd.f zneigh.f zneupd.f zngets.f
	zsortc.f zstatn.f cmout.f cvout.f dmout.f dvout.f icnteq.f
	icopy.f iset.f iswap.f ivout.f second.f smout.f svout.f
	zmout.f zvout.f)

ADD_LIBRARY(arpack SHARED ${arpack_SRCS})
IF(NOT(WIN32))
  INSTALL(TARGETS arpack DESTINATION ${ELMER_INSTALL_LIB_DIR})
ENDIF()

IF(APPLE)
  TARGET_LINK_LIBRARIES(arpack ${BLAS_LIBRARIES} ${LAPACK_LIBRARIES})
ENDIF()

IF(WIN32)
  TARGET_LINK_LIBRARIES(arpack ${BLAS_LIBRARIES} ${LAPACK_LIBRARIES})
  INSTALL(TARGETS arpack DESTINATION "bin")
ENDIF()
