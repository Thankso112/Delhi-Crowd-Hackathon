# V2 vs V4 - same data, same split, same metrics

Tickets: `data/raw/tickets.csv`. Train: features days 1-14 -> target 15-21. Test: features days 8-21 -> target 22-31. Cell = route x weekday/weekend x hour. R2 / MAE on log1p(tickets per day).


## temporal - ALL cells (no outcome filter)

```
                                          model      R2  MAE_log  RMSE_log  MAE_tickets_per_day  Spearman  tier_acc  tier_macroF1
            BASE | shrinkage (own + route-hour)  0.9178   0.1268    0.2301               0.5001    0.8736    0.9278        0.8492
                         V2 | Gradient Boosting  0.9061   0.1382    0.2460               0.5795    0.8383    0.9203        0.8167
                             V2 | Random Forest  0.9034   0.1392    0.2494               0.5685    0.8344    0.9191        0.8146
                         V4 | Gradient Boosting  0.9011   0.1415    0.2525               0.6880    0.8384    0.9204        0.8176
                 BASE | own-history persistence  0.8974   0.1369    0.2571               0.5391    0.8668    0.9200        0.8314
                         V2 | Linear Regression  0.8950   0.1469    0.2600               0.6442    0.8225    0.9166        0.8076
                                V4 | KNN (k=15)  0.8936   0.1456    0.2619               0.6981    0.8432    0.9174        0.8108
                        V4 | SVR (RBF, 12k cap)  0.8934   0.1706    0.2620               0.7208    0.8207    0.9194        0.8156
                                     V2 | Lasso  0.8933   0.1480    0.2622               0.6218    0.8207    0.9159        0.8066
                                       V4 | OLS  0.8927   0.1501    0.2629               0.6955    0.8246    0.9170        0.8083
                                     V4 | Ridge  0.8927   0.1501    0.2629               0.6955    0.8245    0.9170        0.8082
                               V4 | Elastic Net  0.8919   0.1509    0.2639               0.6922    0.8241    0.9165        0.8073
                                     V4 | Lasso  0.8913   0.1513    0.2647               0.6911    0.8233    0.9162        0.8068
                             BASE | global mean -0.0032   0.5835    0.8040               1.8873       NaN    0.7969        0.2957
         V2 | Logistic Regression  [classifier]     NaN      NaN       NaN                  NaN       NaN    0.9222        0.8268
               V2 | GB classifier  [classifier]     NaN      NaN       NaN                  NaN       NaN    0.9227        0.8277
                  V4 | KNN (k=15)  [classifier]     NaN      NaN       NaN                  NaN       NaN    0.9191        0.8197
V4 | SVM (RBF, balanced, 12k cap)  [classifier]     NaN      NaN       NaN                  NaN       NaN    0.9029        0.8301
```

Best R2  -> V2: 0.9061   V4: 0.9011
Best classifier macro-F1 -> V2: 0.8277   V4: 0.8301
Shrinkage baseline R2 = 0.9178  (a model must beat this to add value)

## temporal - cells with >= 10 test tickets

```
                                          model      R2  MAE_log  RMSE_log  MAE_tickets_per_day  Spearman  tier_acc  tier_macroF1
            BASE | shrinkage (own + route-hour)  0.7901   0.2573    0.3377               2.1138    0.8921    0.7929        0.6128
                 BASE | own-history persistence  0.7131   0.2917    0.3947               2.3047    0.8544    0.7751        0.5924
                         V2 | Gradient Boosting  0.6617   0.3327    0.4286               2.6585    0.8649    0.7325        0.5743
                             V2 | Random Forest  0.6562   0.3344    0.4321               2.5819    0.8616    0.7313        0.5705
                         V2 | Linear Regression  0.6358   0.3477    0.4448               2.9944    0.8647    0.7264        0.5628
                                     V2 | Lasso  0.6319   0.3475    0.4471               2.8460    0.8631    0.7233        0.5613
                         V4 | Gradient Boosting  0.6259   0.3526    0.4508               3.3160    0.8646    0.7338        0.5752
                        V4 | SVR (RBF, 12k cap)  0.6258   0.3498    0.4508               3.3116    0.8630    0.7307        0.5725
                                       V4 | OLS  0.6092   0.3638    0.4607               3.3076    0.8681    0.7236        0.5660
                                     V4 | Ridge  0.6092   0.3638    0.4607               3.3075    0.8681    0.7235        0.5659
                               V4 | Elastic Net  0.6078   0.3640    0.4615               3.2811    0.8680    0.7212        0.5645
                                     V4 | Lasso  0.6063   0.3643    0.4624               3.2708    0.8676    0.7204        0.5639
                                V4 | KNN (k=15)  0.6047   0.3623    0.4634               3.3475    0.8569    0.7230        0.5662
                             BASE | global mean -4.6308   1.5859    1.7487               8.7115       NaN    0.0175        0.0114
         V2 | Logistic Regression  [classifier]     NaN      NaN       NaN                  NaN       NaN    0.7576        0.5856
               V2 | GB classifier  [classifier]     NaN      NaN       NaN                  NaN       NaN    0.7619        0.5875
                  V4 | KNN (k=15)  [classifier]     NaN      NaN       NaN                  NaN       NaN    0.7484        0.5801
V4 | SVM (RBF, balanced, 12k cap)  [classifier]     NaN      NaN       NaN                  NaN       NaN    0.8380        0.6077
```

Best R2  -> V2: 0.6617   V4: 0.6259
Best classifier macro-F1 -> V2: 0.5875   V4: 0.6077
Shrinkage baseline R2 = 0.7901  (a model must beat this to add value)

## unseen routes - ALL cells (no outcome filter)

```
                                          model      R2  MAE_log  RMSE_log  MAE_tickets_per_day  Spearman  tier_acc  tier_macroF1
            BASE | shrinkage (own + route-hour)  0.9053   0.1301    0.2339               0.4738    0.8573    0.9298        0.8435
                         V2 | Gradient Boosting  0.8917   0.1412    0.2501               0.5350    0.8262    0.9234        0.8108
                             V2 | Random Forest  0.8885   0.1426    0.2538               0.5334    0.8202    0.9217        0.8045
                         V4 | Gradient Boosting  0.8885   0.1433    0.2538               0.6122    0.8261    0.9239        0.8132
                        V4 | SVR (RBF, 12k cap)  0.8834   0.1705    0.2596               0.6383    0.8002    0.9241        0.8164
                 BASE | own-history persistence  0.8823   0.1400    0.2608               0.5078    0.8455    0.9225        0.8264
                         V2 | Linear Regression  0.8803   0.1488    0.2629               0.5849    0.8080    0.9205        0.8028
                                       V4 | OLS  0.8792   0.1513    0.2642               0.6149    0.8104    0.9200        0.8017
                                     V4 | Ridge  0.8792   0.1514    0.2642               0.6149    0.8104    0.9200        0.8017
                                     V2 | Lasso  0.8785   0.1497    0.2649               0.5676    0.8059    0.9200        0.8038
                               V4 | Elastic Net  0.8782   0.1521    0.2653               0.6134    0.8098    0.9200        0.8026
                                V4 | KNN (k=15)  0.8780   0.1490    0.2654               0.6276    0.8262    0.9188        0.7993
                                     V4 | Lasso  0.8775   0.1524    0.2661               0.6130    0.8089    0.9198        0.8024
                             BASE | global mean -0.0000   0.5614    0.7600               1.6812       NaN    0.8114        0.2986
         V2 | Logistic Regression  [classifier]     NaN      NaN       NaN                  NaN       NaN    0.9239        0.8168
               V2 | GB classifier  [classifier]     NaN      NaN       NaN                  NaN       NaN    0.9245        0.8195
                  V4 | KNN (k=15)  [classifier]     NaN      NaN       NaN                  NaN       NaN    0.9193        0.8075
V4 | SVM (RBF, balanced, 12k cap)  [classifier]     NaN      NaN       NaN                  NaN       NaN    0.9043        0.8257
```

Best R2  -> V2: 0.8917   V4: 0.8885
Best classifier macro-F1 -> V2: 0.8195   V4: 0.8257
Shrinkage baseline R2 = 0.9053  (a model must beat this to add value)

## unseen routes - cells with >= 10 test tickets

```
                                          model      R2  MAE_log  RMSE_log  MAE_tickets_per_day  Spearman  tier_acc  tier_macroF1
            BASE | shrinkage (own + route-hour)  0.7429   0.2780    0.3641               2.1029    0.8725    0.7756        0.6053
                 BASE | own-history persistence  0.6622   0.3101    0.4173               2.2700    0.8346    0.7577        0.5826
                         V2 | Gradient Boosting  0.6045   0.3526    0.4516               2.5556    0.8424    0.7186        0.5663
                             V2 | Random Forest  0.5970   0.3546    0.4559               2.5316    0.8382    0.7096        0.5548
                        V4 | SVR (RBF, 12k cap)  0.5836   0.3630    0.4634               3.0362    0.8505    0.7167        0.5655
                         V2 | Linear Regression  0.5828   0.3636    0.4638               2.8237    0.8429    0.7138        0.5585
                         V4 | Gradient Boosting  0.5800   0.3673    0.4654               3.0617    0.8425    0.7208        0.5672
                                     V2 | Lasso  0.5787   0.3629    0.4661               2.7001    0.8416    0.7115        0.5581
                                       V4 | OLS  0.5634   0.3758    0.4745               3.0219    0.8465    0.7058        0.5552
                                     V4 | Ridge  0.5634   0.3758    0.4745               3.0218    0.8465    0.7058        0.5552
                               V4 | Elastic Net  0.5605   0.3764    0.4761               3.0062    0.8461    0.7061        0.5558
                                     V4 | Lasso  0.5585   0.3766    0.4772               3.0006    0.8457    0.7048        0.5552
                                V4 | KNN (k=15)  0.5437   0.3829    0.4851               3.1239    0.8333    0.6965        0.5480
                             BASE | global mean -4.4793   1.5198    1.6809               7.9946       NaN    0.0189        0.0124
         V2 | Logistic Regression  [classifier]     NaN      NaN       NaN                  NaN       NaN    0.7343        0.5714
               V2 | GB classifier  [classifier]     NaN      NaN       NaN                  NaN       NaN    0.7439        0.5794
                  V4 | KNN (k=15)  [classifier]     NaN      NaN       NaN                  NaN       NaN    0.7240        0.5674
V4 | SVM (RBF, balanced, 12k cap)  [classifier]     NaN      NaN       NaN                  NaN       NaN    0.8333        0.5988
```

Best R2  -> V2: 0.6045   V4: 0.5836
Best classifier macro-F1 -> V2: 0.5794   V4: 0.5988
Shrinkage baseline R2 = 0.7429  (a model must beat this to add value)